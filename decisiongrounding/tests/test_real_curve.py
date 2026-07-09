"""The real adherence-vs-N curve: real PEP decision distractors replace
synthetic `note` filler. These tests are hermetic — they use an in-memory pool,
so they need no network and no built pool on disk."""

from pathlib import Path

import pytest

from providers.base import CorpusArtifact
from scenarios.loader import load_pool, load_scenarios
from scoring.crossover import (
    build_dataset,
    build_dataset_multiseed,
    make_real_distractors,
    merge_seed_datasets,
    run_seeds,
)

_ROOT = Path(__file__).resolve().parent.parent
_REAL = _ROOT / "scenarios_real"


def _pool(n: int) -> list[CorpusArtifact]:
    return [
        CorpusArtifact(
            id=f"PEP-{i:04d}",
            type="decision",
            path=f"corpus/PEP-{i:04d}.md",
            text=f"# PEP-{i:04d}\n\n## Status\n\nFinal\n\nSome real decision body {i}.\n",
        )
        for i in range(1000, 1000 + n)
    ]


def _pilot():
    scenarios = load_scenarios(_REAL)
    disc = [s for s in scenarios if s.scenario_type == "superseded_decision"]
    assert disc, "expected a discriminating real scenario"
    return disc[0]


def test_real_distractors_are_deterministic():
    sc = _pilot()
    pool = _pool(40)
    a = make_real_distractors(pool, 10, sc, seed=0)
    b = make_real_distractors(pool, 10, sc, seed=0)
    assert [x.id for x in a] == [x.id for x in b]
    assert len(a) == 10


def test_real_distractors_exclude_scenario_corpus_ids():
    sc = _pilot()
    own = {a.id for a in sc.corpus}
    # Seed the pool with the scenario's own decision ids; they must never appear.
    pool = _pool(30) + list(sc.corpus)
    drawn = make_real_distractors(pool, 25, sc, seed=1)
    assert own.isdisjoint({x.id for x in drawn})


def test_real_distractors_are_real_decisions_not_filler():
    sc = _pilot()
    drawn = make_real_distractors(_pool(10), 5, sc, seed=0)
    assert all(x.type == "decision" and not x.filler for x in drawn)


def test_build_dataset_with_real_pool_labels_provenance():
    sc_list = load_scenarios(_REAL)
    pool = _pool(30)
    ds = build_dataset(
        sc_list, arms=("context_dump", "naive_rag"), ns=(3, 6), seed=0, pool=pool
    )
    assert ds["distractors"] == "real-decision-pool"
    assert ds["pool_size"] == 30
    # Every arm has a point per N.
    assert len(ds["arms"]["naive_rag"]) == 2


def test_build_dataset_progress_callback_fires_once_per_cell():
    sc_list = load_scenarios(_REAL)
    disc = [s for s in sc_list if s.scenario_type in
            ("conflicting_scoped", "prohibition_at_point_of_action", "superseded_decision")]
    arms = ("context_dump", "naive_rag")
    ns = (3, 6)
    seen: list[dict] = []
    ds = build_dataset(
        sc_list, arms=arms, ns=ns, seed=0, pool=_pool(30), progress=seen.append
    )
    # One cell per (N, arm, discriminating scenario), in order, idx/total correct.
    expected = len(ns) * len(arms) * len(disc)
    assert len(seen) == expected
    assert [r["idx"] for r in seen] == list(range(1, expected + 1))
    assert all(r["total"] == expected for r in seen)
    assert seen[0]["record"] == "cell" and "adherent" in seen[0]
    # The streamed cells reconcile with the final aggregated points.
    assert len(ds["arms"]["naive_rag"]) == len(ns)


def test_build_dataset_real_pool_too_small_raises():
    sc_list = load_scenarios(_REAL)
    with pytest.raises(ValueError, match="pool too small"):
        build_dataset(sc_list, arms=("context_dump",), ns=(10, 500), seed=0, pool=_pool(5))


def test_load_pool_missing_provenance_is_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="provenance"):
        load_pool(tmp_path)


# --- multi-seed aggregation (offline, hermetic) ----------------------------

def test_build_dataset_multiseed_shape_and_ci():
    sc = load_scenarios(_REAL)
    ds = build_dataset_multiseed(
        sc, arms=("context_dump", "naive_rag"), ns=(3, 6), seeds=[0, 1, 2], pool=_pool(30)
    )
    assert ds["n_seeds"] == 3 and ds["seeds"] == [0, 1, 2]
    for arm in ("context_dump", "naive_rag"):
        for p in ds["arms"][arm]:
            assert len(p["adherence_rate_values"]) == 3 and p["n_seeds"] == 3
            lo, hi = p["adherence_rate_ci"]
            assert lo <= p["adherence_rate"] <= hi
            # back-compat: the plain field is still the mean
            assert abs(p["adherence_rate"] - sum(p["adherence_rate_values"]) / 3) < 1e-9


def test_build_dataset_multiseed_single_seed_is_degenerate():
    sc = load_scenarios(_REAL)
    ds = build_dataset_multiseed(sc, arms=("context_dump", "naive_rag"), ns=(3, 6),
                                 seeds=[0], pool=_pool(30))
    assert ds["n_seeds"] == 1
    p = ds["arms"]["naive_rag"][0]
    assert p["adherence_rate_ci"] == [p["adherence_rate"], p["adherence_rate"]]
    assert p["adherence_rate_std"] == 0.0


def test_build_dataset_multiseed_paired_difference():
    sc = load_scenarios(_REAL)
    ds = build_dataset_multiseed(
        sc, arms=("context_dump", "naive_rag"), ns=(3, 6), seeds=[0, 1], pool=_pool(30),
        pair=("context_dump", "naive_rag"),
    )
    assert "paired" in ds
    entries = ds["paired"]["context_dump_vs_naive_rag"]
    assert [e["N"] for e in entries] == [3, 6]
    for e in entries:
        assert len(e["diff_ci"]) == 2 and e["n"] == 2 and len(e["values"]) == 2


def test_build_dataset_multiseed_reports_both_contrasts():
    # A three-arm sweep yields a paired diff for every requested contrast whose
    # arms are present; a contrast with a missing arm is silently skipped.
    sc = load_scenarios(_REAL)
    ds = build_dataset_multiseed(
        sc, arms=("context_dump", "naive_rag", "no_grounding"), ns=(3, 6), seeds=[0, 1],
        pool=_pool(30),
        pairs=[("context_dump", "naive_rag"), ("context_dump", "no_grounding"),
               ("rac", "naive_rag")],  # rac absent -> skipped
    )
    assert set(ds["paired"]) == {"context_dump_vs_naive_rag", "context_dump_vs_no_grounding"}
    for series in ds["paired"].values():
        assert [e["N"] for e in series] == [3, 6]


def test_merge_seed_datasets_augment_equals_fresh_run():
    sc = load_scenarios(_REAL)
    arms, ns = ("context_dump", "naive_rag"), (3, 6)
    pair = ("context_dump", "naive_rag")
    base = build_dataset_multiseed(sc, arms=arms, ns=ns, seeds=[0, 1, 2], pool=_pool(30), pair=pair)
    # add seeds 3,4 WITHOUT re-running 0,1,2
    new_ps = run_seeds(sc, arms, ns, [3, 4], pool=_pool(30))
    merged = merge_seed_datasets(base, new_ps, list(arms), list(ns), pair)
    assert merged["n_seeds"] == 5 and merged["seeds"] == [0, 1, 2, 3, 4]
    # augment must match a fresh 5-seed run
    fresh = build_dataset_multiseed(sc, arms=arms, ns=ns, seeds=[0, 1, 2, 3, 4], pool=_pool(30), pair=pair)
    for arm in arms:
        for pm, pf in zip(merged["arms"][arm], fresh["arms"][arm]):
            assert abs(pm["adherence_rate"] - pf["adherence_rate"]) < 1e-9
            assert sorted(pm["adherence_rate_values"]) == sorted(pf["adherence_rate_values"])


@pytest.mark.parametrize("pool_dir", ["peps_pool", "rfcs_pool"])
def test_committed_pool_loads_when_built(pool_dir):
    # provenance.json is committed (the pin); the corpus is rebuilt on demand and
    # gitignored. Skip when it has not been built locally rather than fail.
    d = _REAL / pool_dir
    if not (d / "provenance.json").exists():
        pytest.skip(f"{pool_dir} provenance not present")
    if not (d / "corpus").exists():
        pytest.skip(f"{pool_dir} corpus not built (run: ingest pool build)")
    pool = load_pool(d)
    assert pool and all(a.type == "decision" and not a.filler for a in pool)
