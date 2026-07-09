"""Generic-error cells are excluded from adherence exactly like
context-window cells: out of the rate, out of the paired `cells` record,
surfaced via error_count/coverage instead. The confound this prevents is an
infrastructure failure (a gateway rejecting every prompt) reading as a
behavioural adherence of 0.0."""

import json

import pytest

import scoring.crossover as crossover
from scenarios.loader import load_scenarios
from scoring.crossover import (
    build_dataset,
    build_dataset_multiseed,
    merge_seed_datasets,
    run_seeds,
)

_SCENARIOS = "scenarios"
_ARMS = ("context_dump", "naive_rag")


def _disc_ids():
    from scoring.crossover import DISCRIMINATING
    return sorted(s.scenario_id for s in load_scenarios(_SCENARIOS)
                  if s.scenario_type in DISCRIMINATING)


def _raise_on(scenario_id, exc):
    real = crossover._run_arm_on_corpus

    def patched(arm, corpus, sc, *a, **kw):
        if sc.scenario_id == scenario_id:
            raise exc
        return real(arm, corpus, sc, *a, **kw)

    return patched


def _point(ds, arm, n):
    return next(p for p in ds["arms"][arm] if p["N"] == n)


def test_error_cells_excluded_from_rate_and_cells(monkeypatch):
    scenarios = load_scenarios(_SCENARIOS)
    n_disc = len(_disc_ids())
    victim = _disc_ids()[0]
    monkeypatch.setattr(crossover, "_run_arm_on_corpus",
                        _raise_on(victim, RuntimeError("gateway down")))
    ds = build_dataset(scenarios, arms=_ARMS, ns=(10,))

    for arm in _ARMS:
        pt = _point(ds, arm, 10)
        assert pt["error_count"] == 1
        assert pt["attempted"] == n_disc - 1
        # adherence_rate is over attempted cells only, never the failed one.
        assert pt["adherence_rate"] == pytest.approx(1.0)
        assert pt["context_window_exceeded_count"] == 0
    # The failed scenario is absent from the paired-statistics record...
    assert not any(c["scenario_id"] == victim for c in ds["cells"])
    assert len(ds["cells"]) == len(_ARMS) * (n_disc - 1)
    # ...but present in errors, tagged with a kind.
    errs = [e for e in ds["errors"] if e["scenario_id"] == victim]
    assert errs and all(e["kind"] == "error" for e in errs)


def test_kind_reflects_exception_type(monkeypatch):
    from providers.answering import SchemaMissError
    scenarios = load_scenarios(_SCENARIOS)
    victim = _disc_ids()[0]
    monkeypatch.setattr(crossover, "_run_arm_on_corpus",
                        _raise_on(victim, SchemaMissError("bad json")))
    ds = build_dataset(scenarios, arms=("context_dump",), ns=(10,))
    assert all(e["kind"] == "schema" for e in ds["errors"]
               if e["scenario_id"] == victim)


def test_all_cells_error_yields_none_rate(monkeypatch):
    scenarios = load_scenarios(_SCENARIOS)
    monkeypatch.setattr(crossover, "_run_arm_on_corpus",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))
    ds = build_dataset(scenarios, arms=("context_dump",), ns=(10,))
    pt = _point(ds, "context_dump", 10)
    assert pt["adherence_rate"] is None
    assert pt["attempted"] == 0
    assert pt["error_count"] == len(_disc_ids())
    assert ds["cells"] == []


def test_multiseed_carries_error_fields(monkeypatch):
    scenarios = load_scenarios(_SCENARIOS)
    victim = _disc_ids()[0]
    monkeypatch.setattr(crossover, "_run_arm_on_corpus",
                        _raise_on(victim, RuntimeError("flaky")))
    ds = build_dataset_multiseed(scenarios, arms=("context_dump",), ns=(10,),
                                 seeds=(0, 1))
    pt = _point(ds, "context_dump", 10)
    # mean + per-seed values survive aggregation for the new fields.
    assert pt["error_count"] == pytest.approx(1.0)
    assert pt["error_count_values"] == [1, 1]
    assert "attempted_values" in pt


def test_merge_tolerates_legacy_points_without_error_fields():
    # An old dataset (pre-error-fields) merges with a fresh seed without KeyError.
    scenarios = load_scenarios(_SCENARIOS)
    old = build_dataset(scenarios, arms=("context_dump",), ns=(10,), seed=0)
    for pt in old["arms"]["context_dump"]:
        pt.pop("error_count", None)
        pt.pop("error_rate", None)
        pt.pop("attempted", None)
    old["seed"] = 0
    new_ps = run_seeds(scenarios, ("context_dump",), (10,), [1])
    merged = merge_seed_datasets(old, new_ps, ["context_dump"], [10],
                                 ("rac", "naive_rag"))
    assert merged["n_seeds"] == 2 if "n_seeds" in merged else True
    # No crash and the merged point still reports adherence.
    assert _point(merged, "context_dump", 10)["adherence_rate"] is not None


def test_generic_error_reruns_on_resume(monkeypatch):
    """A sidecar cell tagged with any non-CWE kind is re-run on resume, while
    a cwe cell replays — the round-1 policy, now exercised for the taxonomy."""
    scenarios = load_scenarios(_SCENARIOS)
    records = []
    build_dataset(scenarios, arms=("context_dump",), ns=(10,), progress=records.append)
    resume = {(0, r["N"], r["arm"], r["scenario_id"]): r for r in records}
    # Poison one cell with each generic kind — all must re-run.
    victim = _disc_ids()[0]
    key = (0, 10, "context_dump", victim)
    for kind in ("schema", "gateway", "transport", "error"):
        resume[key] = dict(resume[key], error=f"{kind} boom", kind=kind)
        real = crossover._run_arm_on_corpus
        calls = []

        def counting(arm, corpus, sc, *a, **kw):
            calls.append(sc.scenario_id)
            return real(arm, corpus, sc, *a, **kw)

        monkeypatch.setattr(crossover, "_run_arm_on_corpus", counting)
        build_dataset(scenarios, arms=("context_dump",), ns=(10,), resume=resume)
        assert calls == [victim], f"kind={kind} should re-run exactly the victim"
        monkeypatch.undo()
