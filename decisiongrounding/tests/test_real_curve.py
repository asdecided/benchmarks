"""The real adherence-vs-N curve: real PEP decision distractors replace
synthetic `note` filler. These tests are hermetic — they use an in-memory pool,
so they need no network and no built pool on disk."""

from pathlib import Path

import pytest

from providers.base import CorpusArtifact
from scenarios.loader import load_pool, load_scenarios
from scoring.crossover import build_dataset, make_real_distractors

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


def test_build_dataset_real_pool_too_small_raises():
    sc_list = load_scenarios(_REAL)
    with pytest.raises(ValueError, match="pool too small"):
        build_dataset(sc_list, arms=("context_dump",), ns=(10, 500), seed=0, pool=_pool(5))


def test_load_pool_missing_provenance_is_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="provenance"):
        load_pool(tmp_path)


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
