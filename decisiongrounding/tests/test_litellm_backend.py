"""Cover the OpenAI-compatible (LiteLLM) answering backend.

Offline throughout: request-shape and parse tests construct the adapter
without a network, and the one full ``respond()`` round-trip runs against a
stdlib ``http.server`` mock speaking ``/chat/completions`` on localhost. The
held-constant contract is the point under test — the litellm backend must
send the SAME scaffold, user prompt, and ProposedChange schema as the
Anthropic-native backend, differing only in wire format.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from providers import OpenAICompatAnsweringModel, make_answering_model
from providers.answering import ClaudeAnsweringModel, _PROPOSED_CHANGE_SCHEMA
from providers.base import SCAFFOLD, GroundingContext, ProposedChange, Task

GROUNDING = GroundingContext(
    text="(test) no real grounding.", artifacts_supplied=(), token_estimate=1
)
TASK = Task(prompt="Test the adapter.", proposed_action="do nothing")

GOOD_ANSWER = {
    "summary": "No live decision prohibits this action; proceed.",
    "actions": [{"kind": "implement", "target": "proposed_action", "detail": "do nothing"}],
    "cites_decisions": ["DG-ADR-TEST-001"],
    "asserts_prohibition": False,
    "asserts_permission": True,
}


def _payload(content: str | None, finish_reason: str = "stop", usage: dict | None = None):
    message = {"role": "assistant", "content": content}
    payload = {"choices": [{"message": message, "finish_reason": finish_reason}]}
    if usage is not None:
        payload["usage"] = usage
    return payload


# --- factory routing ---------------------------------------------------------


def test_make_answering_model_routes_litellm_spec():
    model = make_answering_model("litellm:claude-opus-4-8", seed=3)
    assert isinstance(model, OpenAICompatAnsweringModel)
    assert model.model == "claude-opus-4-8"
    assert model.version == "litellm:claude-opus-4-8"
    assert model.seed == 3


def test_make_answering_model_still_rejects_unknown():
    with pytest.raises(ValueError, match="litellm:<model-alias>"):
        make_answering_model("openai", seed=0)


def test_litellm_spec_requires_an_alias():
    with pytest.raises(ValueError):
        make_answering_model("litellm:", seed=0)


# --- held-constant contract: same scaffold, prompt, and schema as claude -----


def test_request_shares_prompt_and_schema_with_claude_backend():
    litellm = OpenAICompatAnsweringModel(model="alias")
    claude = ClaudeAnsweringModel()
    lite_req = litellm.build_request(SCAFFOLD, GROUNDING, TASK)
    claude_req = claude.build_request(SCAFFOLD, GROUNDING, TASK)

    assert lite_req["messages"][0] == {"role": "system", "content": SCAFFOLD}
    assert claude_req["system"] == SCAFFOLD
    # Identical user message across transports.
    assert lite_req["messages"][1]["content"] == claude_req["messages"][0]["content"]
    # Identical structured-output schema, in each surface's native envelope.
    assert (
        lite_req["response_format"]["json_schema"]["schema"]
        == claude_req["output_config"]["format"]["schema"]
        == _PROPOSED_CHANGE_SCHEMA
    )
    assert lite_req["response_format"]["json_schema"]["strict"] is True
    assert lite_req["model"] == "alias"


# --- parsing -----------------------------------------------------------------


def test_parse_response_decodes_proposed_change():
    model = OpenAICompatAnsweringModel(model="alias")
    pc = model.parse_response(_payload(json.dumps(GOOD_ANSWER)))
    assert isinstance(pc, ProposedChange)
    assert pc.asserts_permission is True
    assert pc.cites_decisions == ["DG-ADR-TEST-001"]
    assert pc.actions[0].kind == "implement"


def test_parse_response_maps_content_filter_to_refusal():
    model = OpenAICompatAnsweringModel(model="alias")
    pc = model.parse_response(_payload(None, finish_reason="content_filter"))
    assert pc.summary == "model refused"
    assert pc.actions == [] and pc.cites_decisions == []
    assert pc.asserts_prohibition is False and pc.asserts_permission is False


def test_parse_response_fails_loudly_on_non_json():
    model = OpenAICompatAnsweringModel(model="alias")
    with pytest.raises(RuntimeError, match="non-JSON"):
        model.parse_response(_payload("not json at all"))


def test_parse_response_fails_loudly_on_missing_field():
    incomplete = dict(GOOD_ANSWER)
    del incomplete["cites_decisions"]
    model = OpenAICompatAnsweringModel(model="alias")
    with pytest.raises(RuntimeError, match="missing an expected"):
        model.parse_response(_payload(json.dumps(incomplete)))


def test_parse_usage_normalises_openai_shape():
    model = OpenAICompatAnsweringModel(model="alias")
    usage = model.parse_usage({"usage": {"prompt_tokens": 12, "completion_tokens": 34}})
    assert usage == {"input_tokens": 12, "output_tokens": 34}
    assert model.parse_usage({}) is None
    assert model.parse_usage({"usage": {}}) is None


# --- full round-trip against a localhost mock gateway ------------------------


class _MockGateway(BaseHTTPRequestHandler):
    """A minimal /chat/completions endpoint recording the request it saw."""

    seen: dict = {}

    def do_POST(self):  # noqa: N802 (http.server naming)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        _MockGateway.seen = {
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "body": body,
        }
        response = json.dumps(
            _payload(
                json.dumps(GOOD_ANSWER),
                usage={"prompt_tokens": 21, "completion_tokens": 8},
            )
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *args):  # silence request logging in test output
        pass


def test_respond_round_trip_via_mock_gateway(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockGateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        monkeypatch.setenv("LITELLM_BASE_URL", f"http://{host}:{port}")
        monkeypatch.setenv("LITELLM_API_KEY", "sk-test-virtual-key")

        model = make_answering_model("litellm:claude-opus-4-8", seed=0)
        pc = model.respond(SCAFFOLD, GROUNDING, TASK)

        assert pc.asserts_permission is True
        assert model.last_usage == {"input_tokens": 21, "output_tokens": 8}
        assert _MockGateway.seen["path"] == "/chat/completions"
        assert _MockGateway.seen["authorization"] == "Bearer sk-test-virtual-key"
        assert _MockGateway.seen["body"]["model"] == "claude-opus-4-8"
        assert (
            _MockGateway.seen["body"]["response_format"]["json_schema"]["schema"]
            == _PROPOSED_CHANGE_SCHEMA
        )
    finally:
        server.shutdown()
        server.server_close()


def test_probe_openai_mode_ignores_anthropic_base_url(monkeypatch):
    """Regression: with both gateways' env vars set (common on enterprise
    hosts), the openai-mode probe must target LITELLM_BASE_URL, not the
    ANTHROPIC_BASE_URL the native mode reads."""
    from scripts import litellm_probe

    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockGateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com")
        monkeypatch.setenv("LITELLM_BASE_URL", f"http://{host}:{port}")
        monkeypatch.setenv("LITELLM_API_KEY", "sk-test-virtual-key")
        assert litellm_probe.main(["--mode", "openai", "--model", "alias"]) == 0
        assert _MockGateway.seen["body"]["model"] == "alias"
    finally:
        server.shutdown()
        server.server_close()


def test_respond_requires_gateway_configuration(monkeypatch):
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    model = OpenAICompatAnsweringModel(model="alias")
    with pytest.raises(RuntimeError, match="LITELLM_BASE_URL"):
        model.respond(SCAFFOLD, GROUNDING, TASK)
