"""Cell-granular crash resume: --resume replays completed cells from the
durable .partial.jsonl sidecar instead of re-running them."""

import json
from pathlib import Path

import pytest

import scoring.crossover as crossover
from runner.cli import _load_resume_cells, main
from scenarios.loader import load_scenarios
from scoring.crossover import build_dataset

_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS = _ROOT / "scenarios"

_ARMS = ("context_dump", "naive_rag")
_NS = (10, 50)


def _cell_line(seed=None, n=10, arm="naive_rag", scenario_id="s1", **over):
    rec = {"record": "cell", "idx": 1, "total": 8, "N": n, "arm": arm,
           "scenario_id": scenario_id, "adherent": True,
           "stale_decision_followed": False, "governing_decision_retrieved": True,
           "token_estimate": 123, "usage": None, "error": None, "kind": None}
    if seed is not None:
        rec["seed"] = seed
    rec.update(over)
    return rec


def _sweep(scenarios, progress=None, resume=None, seed=0):
    return build_dataset(scenarios, arms=_ARMS, ns=_NS, seed=seed,
                         progress=progress, resume=resume)


def _resume_from(records, seed=0):
    return {(rec.get("seed", seed), rec["N"], rec["arm"], rec["scenario_id"]): rec
            for rec in records}


# ---------------------------------------------------------------- loader


def test_load_resume_cells_keys_and_default_seed(tmp_path):
    p = tmp_path / "run-x-crossover.partial.jsonl"
    lines = [
        _cell_line(seed=2, n=50, arm="rac", scenario_id="tagged"),
        _cell_line(n=10, arm="naive_rag", scenario_id="seedless"),
        {"record": "run", "arm": "naive_rag", "scenario_id": "base-table-line"},
        {"record": "error", "arm": "rac", "scenario_id": "base-err"},
    ]
    p.write_text("".join(json.dumps(line) + "\n" for line in lines)
                 + '{"record": "ce',  # crash-truncated final append
                 encoding="utf-8")
    cells = _load_resume_cells(p, default_seed=7)
    assert set(cells) == {(2, 50, "rac", "tagged"), (7, 10, "naive_rag", "seedless")}


def test_load_resume_cells_last_write_wins(tmp_path):
    p = tmp_path / "run-x-crossover.partial.jsonl"
    first = _cell_line(seed=0, adherent=True)
    second = _cell_line(seed=0, adherent=False)
    p.write_text(json.dumps(first) + "\n" + json.dumps(second) + "\n",
                 encoding="utf-8")
    cells = _load_resume_cells(p, default_seed=0)
    assert cells[(0, 10, "naive_rag", "s1")]["adherent"] is False


# ---------------------------------------------------------- build_dataset


def test_resume_skips_completed_cells_and_is_results_identical(monkeypatch):
    scenarios = load_scenarios(_SCENARIOS)
    records: list[dict] = []
    ds1 = _sweep(scenarios, progress=records.append)
    assert records, "sweep produced no progress records"

    calls = []

    def boom(*a, **kw):
        calls.append(a)
        raise RuntimeError("resume should never run a cached cell live")

    monkeypatch.setattr(crossover, "_run_arm_on_corpus", boom)
    ds2 = _sweep(scenarios, resume=_resume_from(records))
    assert calls == []
    assert json.dumps(ds1, sort_keys=True) == json.dumps(ds2, sort_keys=True)


def test_resume_replayed_cells_fire_progress_tagged_cached():
    scenarios = load_scenarios(_SCENARIOS)
    records: list[dict] = []
    _sweep(scenarios, progress=records.append)
    replayed: list[dict] = []
    _sweep(scenarios, progress=replayed.append, resume=_resume_from(records))
    assert len(replayed) == len(records)
    assert all(rec.get("cached") is True for rec in replayed)
    assert not any(rec.get("cached") for rec in records)


def test_resume_reruns_errored_cells(monkeypatch):
    scenarios = load_scenarios(_SCENARIOS)
    records: list[dict] = []
    ds1 = _sweep(scenarios, progress=records.append)
    resume = _resume_from(records)
    # Poison one cached cell with a transient error — it must re-run live.
    err_key = sorted(resume)[0]
    resume[err_key] = dict(resume[err_key], error="RuntimeError('flaky gateway')")

    real = crossover._run_arm_on_corpus
    calls = []

    def counting(arm, corpus, sc, *a, **kw):
        calls.append((arm, sc.scenario_id))
        return real(arm, corpus, sc, *a, **kw)

    monkeypatch.setattr(crossover, "_run_arm_on_corpus", counting)
    ds2 = _sweep(scenarios, resume=resume)
    assert calls == [(err_key[2], err_key[3])]
    # The re-run recovered the cell — same dataset as an uninterrupted run.
    assert json.dumps(ds1, sort_keys=True) == json.dumps(ds2, sort_keys=True)


def test_resume_replays_context_window_exceeded(monkeypatch):
    scenarios = load_scenarios(_SCENARIOS)
    records: list[dict] = []
    _sweep(scenarios, progress=records.append)
    resume = _resume_from(records)
    cwe_key = sorted(k for k in resume if k[2] == "naive_rag")[0]
    resume[cwe_key] = dict(
        resume[cwe_key], adherent=False, stale_decision_followed=False,
        governing_decision_retrieved=None, token_estimate=999, usage=None,
        error="ContextWindowExceededError('too big')",
        kind="context_window_exceeded",
    )

    def boom(*a, **kw):
        raise AssertionError("no cell should run live")

    monkeypatch.setattr(crossover, "_run_arm_on_corpus", boom)
    ds = _sweep(scenarios, resume=resume)
    assert {"arm": cwe_key[2], "scenario_id": cwe_key[3], "N": cwe_key[1],
            "error": "ContextWindowExceededError('too big')",
            "kind": "context_window_exceeded"} in ds["errors"]
    pt = next(p for p in ds["arms"][cwe_key[2]] if p["N"] == cwe_key[1])
    assert pt["context_window_exceeded_count"] == 1
    # A never-answered cell stays out of the paired-statistics record.
    assert not any(c["arm"] == cwe_key[2] and c["N"] == cwe_key[1]
                   and c["scenario_id"] == cwe_key[3] for c in ds["cells"])


def test_resume_seed_mismatch_not_used(monkeypatch):
    scenarios = load_scenarios(_SCENARIOS)
    records: list[dict] = []
    _sweep(scenarios, progress=records.append, seed=0)
    wrong_seed = _resume_from(records, seed=1)  # cache is for seed 1

    real = crossover._run_arm_on_corpus
    calls = []

    def counting(*a, **kw):
        calls.append(a)
        return real(*a, **kw)

    monkeypatch.setattr(crossover, "_run_arm_on_corpus", counting)
    _sweep(scenarios, resume=wrong_seed, seed=0)
    assert len(calls) == len(records)  # every cell ran live


# ------------------------------------------------------------------ CLI


def _demo_args(tmp_path, *extra):
    return ["demo", "--scenarios", str(_SCENARIOS), "--out", str(tmp_path),
            "--ns", "10,50", *extra]


def test_demo_resume_auto_end_to_end(tmp_path, monkeypatch, capsys):
    assert main(_demo_args(tmp_path)) == 0
    sidecars = list(tmp_path.glob("run-*-crossover.partial.jsonl"))
    assert len(sidecars) == 1
    ds_fresh = json.loads((tmp_path / "crossover_dataset.json").read_text())

    def boom(*a, **kw):
        raise AssertionError("resume auto should replay every sweep cell")

    monkeypatch.setattr(crossover, "_run_arm_on_corpus", boom)
    assert main(_demo_args(tmp_path, "--resume", "auto")) == 0
    err = capsys.readouterr().err
    assert "(resume:" in err
    assert "cached" in err
    ds_resumed = json.loads((tmp_path / "crossover_dataset.json").read_text())
    assert json.dumps(ds_fresh, sort_keys=True) == json.dumps(ds_resumed, sort_keys=True)


def test_demo_sidecar_records_are_seed_tagged(tmp_path):
    assert main(_demo_args(tmp_path, "--seed", "3")) == 0
    sidecar = next(iter(tmp_path.glob("run-*-crossover.partial.jsonl")))
    recs = [json.loads(line) for line in sidecar.read_text().splitlines()]
    cells = [r for r in recs if r.get("record") == "cell"]
    assert cells and all(r["seed"] == 3 for r in cells)


def test_resume_rejects_augment(tmp_path):
    with pytest.raises(SystemExit, match="mutually exclusive"):
        main(_demo_args(tmp_path, "--resume", "x.jsonl", "--augment", "y.json"))


def test_batched_resume_skips_submission(monkeypatch):
    """A cached cell is never assembled or submitted to the batch — only the
    missing cells pay."""
    import types

    from providers.answering import ClaudeAnsweringModel
    from scoring.crossover import build_dataset_batched
    from tests.test_batch import _FakeBatches

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake_batches = _FakeBatches()
    fake = types.SimpleNamespace(messages=types.SimpleNamespace(batches=fake_batches))
    monkeypatch.setattr(ClaudeAnsweringModel, "_ensure_client", lambda self: fake)

    scenarios = load_scenarios(_SCENARIOS)
    arms = ("context_dump", "no_grounding")
    records: list[dict] = []
    ds1 = build_dataset_batched(scenarios, arms=arms, ns=(3, 6), seed=0,
                                embedder_spec="local-hash", poll=0,
                                progress=records.append)
    n_cells = len(records)
    submitted_fresh = len(fake_batches._requests)
    assert submitted_fresh == n_cells

    # Resume with every cell cached except one — exactly one request submitted.
    resume = _resume_from(records)
    missing = sorted(resume)[0]
    del resume[missing]
    replayed: list[dict] = []
    ds2 = build_dataset_batched(scenarios, arms=arms, ns=(3, 6), seed=0,
                                embedder_spec="local-hash", poll=0,
                                progress=replayed.append, resume=resume)
    assert len(fake_batches._requests) == 1
    assert sum(1 for r in replayed if r.get("cached")) == n_cells - 1
    assert json.dumps(ds1, sort_keys=True) == json.dumps(ds2, sort_keys=True)


def test_batched_resume_fully_cached_never_touches_the_client(monkeypatch):
    import types

    from providers.answering import ClaudeAnsweringModel
    from scoring.crossover import build_dataset_batched
    from tests.test_batch import _FakeBatches

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    fake = types.SimpleNamespace(messages=types.SimpleNamespace(batches=_FakeBatches()))
    monkeypatch.setattr(ClaudeAnsweringModel, "_ensure_client", lambda self: fake)
    scenarios = load_scenarios(_SCENARIOS)
    records: list[dict] = []
    ds1 = build_dataset_batched(scenarios, arms=("context_dump",), ns=(3,), seed=0,
                                embedder_spec="local-hash", poll=0,
                                progress=records.append)

    def no_client(self):
        raise AssertionError("fully-cached resume must not build a client")

    monkeypatch.setattr(ClaudeAnsweringModel, "_ensure_client", no_client)
    ds2 = build_dataset_batched(scenarios, arms=("context_dump",), ns=(3,), seed=0,
                                embedder_spec="local-hash", poll=0,
                                resume=_resume_from(records))
    assert json.dumps(ds1, sort_keys=True) == json.dumps(ds2, sort_keys=True)


def test_resume_auto_with_no_sidecar_fails_clearly(tmp_path):
    with pytest.raises(SystemExit, match="no run-.*crossover.partial.jsonl"):
        main(_demo_args(tmp_path, "--resume", "auto"))


def test_resume_missing_path_fails_clearly(tmp_path):
    with pytest.raises(SystemExit, match="not found"):
        main(_demo_args(tmp_path, "--resume", str(tmp_path / "nope.jsonl")))
