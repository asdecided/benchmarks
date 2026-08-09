"""Downstream adherence checks for Core's graph-boost lexical floor."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path

import pytest

from providers import ScriptedAnsweringModel, build_provider
from scenarios.loader import load_scenarios
from scoring.scorer import score

_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS = _ROOT / "scenarios_retrieval_gate"
_SCHEMA = _ROOT / "schema" / "scenario.schema.json"
_DECIDED_BIN = os.environ.get("DECIDED_BIN", "decided")
_HAS_CORE = shutil.which(_DECIDED_BIN) is not None
_GOVERNING = "DGG-6A7E1EC1CA11"


def _cases():
    return load_scenarios(_SCENARIOS)


def test_retrieval_gate_scenarios_are_focused_and_schema_valid():
    cases = _cases()
    assert [case.scenario_id for case in cases] == [
        "graph_boost_gate_archive",
        "graph_boost_gate_lifecycle",
    ]
    for case in cases:
        assert case.binding_decisions == (_GOVERNING,)
        assert len(case.corpus) == 9
        try:
            import jsonschema
        except ImportError:
            continue
        raw = json.loads((case.directory / "scenario.json").read_text(encoding="utf-8"))
        jsonschema.validate(raw, json.loads(_SCHEMA.read_text(encoding="utf-8")))


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case.scenario_id)
def test_retrieval_gate_scenarios_discriminate_offline(case):
    context = build_provider("context_dump", ScriptedAnsweringModel(seed=0))
    context.prepare(list(case.corpus))
    assert score(case, context.respond(case.task)).adherent

    empty = build_provider("no_grounding", ScriptedAnsweringModel(seed=0))
    empty.prepare(list(case.corpus))
    assert not score(case, empty.respond(case.task)).adherent


@pytest.mark.skipif(not _HAS_CORE, reason="AsDecided Core CLI not on PATH")
@pytest.mark.parametrize("case", _cases(), ids=lambda case: case.scenario_id)
def test_graph_floor_keeps_governing_decision_inside_agent_budget(case):
    arm = build_provider("rac", ScriptedAnsweringModel(seed=0))
    arm.prepare(list(case.corpus))
    proposed = arm.respond(case.task)

    assert _GOVERNING in arm.grounding.artifacts_supplied
    assert arm.grounding.artifacts_supplied[0] == _GOVERNING
    result = score(case, proposed)
    assert result.adherent
    assert result.governing_decision_matched
