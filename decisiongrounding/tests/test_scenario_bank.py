"""The synthetic discriminating-scenario bank: graded lexical overlap, each
scenario satisfying the offline gate (context_dump adheres, no_grounding
fails), and a crossover smoke over the enlarged bank. Expanding from 3 to 15
discriminating scenarios is the response to the pilot's biggest weakness —
12 of 13 failures came from a single scenario."""

import json
from pathlib import Path

import pytest

from providers import ScriptedAnsweringModel, build_provider
from scenarios.loader import load_scenarios
from scenarios.overlap import measured_overlap, overlap_band
from scoring.crossover import DISCRIMINATING, build_dataset
from scoring.scorer import score

_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS = _ROOT / "scenarios"
_SCHEMA = _ROOT / "schema" / "scenario.schema.json"

# The scenarios authored as the graded bank (the three original discriminating
# scenarios keep their own ids and are covered by test_arms_smoke/test_overlap).
_BANK_PREFIXES = ("prohibition_", "superseded_", "conflicting_")
_ORIGINAL = {"conflicting_scoped_retry", "prohibition_language_migration",
             "superseded_decision"}


def _bank():
    return [s for s in load_scenarios(_SCENARIOS)
            if s.scenario_id.startswith(_BANK_PREFIXES)
            and s.scenario_id not in _ORIGINAL]


def _discriminating():
    return [s for s in load_scenarios(_SCENARIOS)
            if s.scenario_type in DISCRIMINATING]


def test_bank_has_at_least_twelve_new_scenarios():
    assert len(_bank()) >= 12
    assert len(_discriminating()) >= 15


@pytest.mark.parametrize("sc", _bank(), ids=lambda s: s.scenario_id)
def test_bank_scenario_passes_offline_gate(sc):
    """context_dump (sees everything) must adhere; no_grounding (sees nothing)
    must not — the discrimination gate every real scenario must clear."""
    model = ScriptedAnsweringModel(seed=0)
    cd = build_provider("context_dump", model)
    cd.prepare(list(sc.corpus))
    assert score(sc, cd.respond(sc.task)).adherent, f"{sc.scenario_id}: context_dump should adhere"
    ng = build_provider("no_grounding", model)
    ng.prepare(list(sc.corpus))
    assert not score(sc, ng.respond(sc.task)).adherent, f"{sc.scenario_id}: no_grounding should fail"


@pytest.mark.parametrize("sc", _bank(), ids=lambda s: s.scenario_id)
def test_bank_scenario_declares_measured_overlap(sc):
    assert sc.lexical_overlap is not None
    assert overlap_band(measured_overlap(sc)) == sc.lexical_overlap


@pytest.mark.parametrize("sc", _bank(), ids=lambda s: s.scenario_id)
def test_bank_scenario_is_schema_valid(sc):
    try:
        import jsonschema
    except ImportError:
        pytest.skip("jsonschema not installed")
    raw = json.loads((sc.directory / "scenario.json").read_text())
    jsonschema.validate(raw, json.loads(_SCHEMA.read_text()))


def test_bank_covers_the_type_by_overlap_matrix():
    """Every (discriminating type, overlap band) cell has at least one
    scenario — the graded design the feedback asked for."""
    cells = {(s.scenario_type, s.lexical_overlap)
             for s in _discriminating() if s.lexical_overlap}
    for stype in DISCRIMINATING:
        for band in ("high", "medium", "low"):
            assert (stype, band) in cells, f"missing {stype} x {band}"


def test_scoring_is_deterministic_across_runs():
    sc = _bank()[0]
    model = ScriptedAnsweringModel(seed=0)
    p1 = build_provider("context_dump", model)
    p1.prepare(list(sc.corpus))
    a = score(sc, p1.respond(sc.task))
    p2 = build_provider("context_dump", ScriptedAnsweringModel(seed=0))
    p2.prepare(list(sc.corpus))
    b = score(sc, p2.respond(sc.task))
    assert a.adherent == b.adherent and a.stale_decision_followed == b.stale_decision_followed


def test_enlarged_bank_crossover_shows_naive_rag_degrading():
    scenarios = load_scenarios(_SCENARIOS)
    ds = build_dataset(scenarios, arms=("context_dump", "naive_rag"), ns=(10, 300))
    cd = [p["adherence_rate"] for p in ds["arms"]["context_dump"]]
    nr = [p["adherence_rate"] for p in ds["arms"]["naive_rag"]]
    assert all(x == 1.0 for x in cd)          # whole-corpus arm holds
    assert nr[-1] < 1.0                        # retrieval degrades at large N
