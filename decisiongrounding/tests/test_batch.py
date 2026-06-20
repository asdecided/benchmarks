"""Batch runner mode + the assemble/respond split it relies on. Hermetic: a
fake Batch-API client stands in for Anthropic, so the build -> submit -> poll ->
collect -> score wiring is exercised with no network and no spend."""

import json
import types
from pathlib import Path

import pytest

from providers import ScriptedAnsweringModel, build_provider
from providers.answering import ClaudeAnsweringModel
from providers.base import SCAFFOLD
from runner.cli import cmd_batch
from scenarios.loader import load_scenarios

_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS = _ROOT / "scenarios"


# --- the assemble/respond split -------------------------------------------

def test_assemble_is_task_dependent_and_drives_respond():
    scenarios = load_scenarios(_SCENARIOS)
    sc = scenarios[0]
    p = build_provider("naive_rag", ScriptedAnsweringModel(seed=0))
    p.prepare(list(sc.corpus))
    g = p.assemble(sc.task)
    # assemble() returns the grounding it would feed the answering model, and
    # leaves it on the provider — no answering-model call happened.
    assert g.text and g is p.grounding
    # respond() still works and routes through assemble().
    pc = p.respond(sc.task)
    assert pc.summary


def test_build_request_and_parse_message_roundtrip():
    m = ClaudeAnsweringModel()
    scenarios = load_scenarios(_SCENARIOS)
    sc = scenarios[0]
    p = build_provider("context_dump", m)
    p.prepare(list(sc.corpus))
    req = m.build_request(SCAFFOLD, p.assemble(sc.task), sc.task)
    assert req["model"] == m.version and req["system"] == SCAFFOLD
    assert req["output_config"]["format"]["type"] == "json_schema"
    # parse a fake Messages response (same shape as a Batch result's .message)
    payload = json.dumps({
        "summary": "ok", "actions": [], "cites_decisions": ["X"],
        "asserts_prohibition": False, "asserts_permission": True,
    })
    msg = types.SimpleNamespace(
        stop_reason="end_turn",
        content=[types.SimpleNamespace(type="text", text=payload)],
    )
    pc = m.parse_message(msg)
    assert pc.asserts_permission and pc.cites_decisions == ["X"]


# --- the batch runner, against a fake Batch-API client --------------------

class _FakeBatches:
    """Minimal stand-in for client.messages.batches."""

    def __init__(self):
        self._requests = None

    def create(self, requests):
        self._requests = list(requests)
        return types.SimpleNamespace(id="batch_test", processing_status="in_progress")

    def retrieve(self, _id):  # immediately ended — no polling sleep
        rc = types.SimpleNamespace(processing=0, succeeded=len(self._requests), errored=0)
        return types.SimpleNamespace(id="batch_test", processing_status="ended", request_counts=rc)

    def results(self, _id):
        payload = json.dumps({
            "summary": "proceed", "actions": [], "cites_decisions": ["X"],
            "asserts_prohibition": False, "asserts_permission": True,
        })
        for req in self._requests:
            msg = types.SimpleNamespace(
                stop_reason="end_turn",
                content=[types.SimpleNamespace(type="text", text=payload)],
                usage=types.SimpleNamespace(input_tokens=1500, output_tokens=40),
            )
            yield types.SimpleNamespace(
                custom_id=req["custom_id"],
                result=types.SimpleNamespace(type="succeeded", message=msg),
            )


def test_cmd_batch_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")  # satisfies preflight
    fake = types.SimpleNamespace(messages=types.SimpleNamespace(batches=_FakeBatches()))
    monkeypatch.setattr(ClaudeAnsweringModel, "_ensure_client", lambda self: fake)

    args = types.SimpleNamespace(
        arms="context_dump,no_grounding", answering="claude", embedder="local-hash",
        scenarios=str(_SCENARIOS), out=str(tmp_path), seed=0, poll=0,
    )
    rc = cmd_batch(args)
    assert rc == 0  # no errors

    report = json.loads(next(tmp_path.glob("run-*-batch-*.json")).read_text())
    n = len(load_scenarios(_SCENARIOS))
    assert len(report["runs"]) == 2 * n  # two arms x scenarios
    assert report["errors"] == []
    for run in report["runs"]:
        assert run["arm"] in ("context_dump", "no_grounding")
        assert "score" in run and "proposed_change" in run
        assert run["answering_model"]["version"] == "claude-opus-4-8"
        # batch results carry real token usage -> the cost report can use it.
        assert run["usage"] == {"input_tokens": 1500, "output_tokens": 40}


def test_cmd_batch_rejects_offline_stub(tmp_path):
    args = types.SimpleNamespace(
        arms="context_dump", answering="offline-stub", embedder="local-hash",
        scenarios=str(_SCENARIOS), out=str(tmp_path), seed=0, poll=0,
    )
    with pytest.raises(SystemExit, match="requires --answering claude"):
        cmd_batch(args)
