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
from providers.answering import (
    SCHEMA_MISS_MAX_RETRIES,
    ClaudeAnsweringModel,
    SchemaMissError,
    _PROPOSED_CHANGE_SCHEMA,
)
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


def _tool_call_payload(answer: dict, usage: dict | None = None):
    """The tool/function-calling analogue of `_payload`, for the fallback path."""
    message = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "propose_change", "arguments": json.dumps(answer)},
            }
        ],
    }
    payload = {"choices": [{"message": message, "finish_reason": "tool_calls"}]}
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


def test_parse_response_missing_field_is_a_schema_miss():
    # SchemaMissError is a RuntimeError subclass (existing callers/tests that
    # catch RuntimeError keep working), but retry logic can catch it specifically.
    incomplete = dict(GOOD_ANSWER)
    del incomplete["cites_decisions"]
    model = OpenAICompatAnsweringModel(model="alias")
    with pytest.raises(SchemaMissError):
        model.parse_response(_payload(json.dumps(incomplete)))


def test_parse_response_no_choices_is_a_schema_miss():
    model = OpenAICompatAnsweringModel(model="alias")
    with pytest.raises(SchemaMissError, match="no choices"):
        model.parse_response({"choices": []})


# --- tool/function-calling fallback request shape + parsing -----------------


def test_build_tool_call_request_shares_prompt_and_schema():
    model = OpenAICompatAnsweringModel(model="alias")
    req = model.build_request(SCAFFOLD, GROUNDING, TASK)
    tool_req = model.build_tool_call_request(SCAFFOLD, GROUNDING, TASK)
    assert tool_req["messages"] == req["messages"]
    assert "response_format" not in tool_req
    fn = tool_req["tools"][0]["function"]
    assert fn["name"] == "propose_change"
    assert fn["parameters"] == _PROPOSED_CHANGE_SCHEMA
    assert tool_req["tool_choice"] == {"type": "function", "function": {"name": "propose_change"}}


def test_parse_tool_call_response_decodes_proposed_change():
    model = OpenAICompatAnsweringModel(model="alias")
    pc = model.parse_tool_call_response(_tool_call_payload(GOOD_ANSWER))
    assert pc.asserts_permission is True
    assert pc.cites_decisions == ["DG-ADR-TEST-001"]


def test_parse_tool_call_response_fails_loudly_on_no_tool_calls():
    model = OpenAICompatAnsweringModel(model="alias")
    with pytest.raises(SchemaMissError, match="no tool_calls"):
        model.parse_tool_call_response(_payload("not used", finish_reason="stop"))


def test_parse_tool_call_response_maps_content_filter_to_refusal():
    model = OpenAICompatAnsweringModel(model="alias")
    pc = model.parse_tool_call_response(_payload(None, finish_reason="content_filter"))
    assert pc.summary == "model refused"


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


# --- schema-miss retry + tool-call fallback, end-to-end ----------------------


class _ScriptedGateway(BaseHTTPRequestHandler):
    """Replays one scripted `/chat/completions` response per request (in
    order), recording every request body it saw — lets a test exercise
    retry/fallback behaviour across a sequence of gateway responses."""

    responses: list = []
    seen_requests: list = []

    def do_POST(self):  # noqa: N802 (http.server naming)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        idx = len(_ScriptedGateway.seen_requests)
        _ScriptedGateway.seen_requests.append(body)
        payload = _ScriptedGateway.responses[idx]
        response = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *args):  # silence request logging in test output
        pass


def _run_scripted(monkeypatch, responses, **model_kwargs):
    """Serve `responses` in order from a fresh mock gateway and return
    (model, proposed_change, seen_requests)."""
    _ScriptedGateway.responses = responses
    _ScriptedGateway.seen_requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ScriptedGateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        monkeypatch.setenv("LITELLM_BASE_URL", f"http://{host}:{port}")
        monkeypatch.setenv("LITELLM_API_KEY", "sk-test-virtual-key")
        model = OpenAICompatAnsweringModel(model="alias", **model_kwargs)
        pc = model.respond(SCAFFOLD, GROUNDING, TASK)
        return model, pc, list(_ScriptedGateway.seen_requests)
    finally:
        server.shutdown()
        server.server_close()


_INCOMPLETE_ANSWER = {k: v for k, v in GOOD_ANSWER.items() if k != "cites_decisions"}


def test_respond_retries_identical_request_on_schema_miss(monkeypatch):
    model, pc, seen = _run_scripted(
        monkeypatch,
        [
            _payload(json.dumps(_INCOMPLETE_ANSWER)),
            _payload(json.dumps(_INCOMPLETE_ANSWER)),
            _payload(json.dumps(GOOD_ANSWER), usage={"prompt_tokens": 5, "completion_tokens": 2}),
        ],
    )
    assert pc.asserts_permission is True
    assert model.last_usage == {"input_tokens": 5, "output_tokens": 2}
    assert len(seen) == 3
    assert seen[0] == seen[1] == seen[2]  # every resend is the IDENTICAL request
    assert model.last_schema_retries == 2  # 2 misses before the 3rd attempt succeeded
    assert model.last_used_tool_call_fallback is False


def test_respond_default_max_retries_matches_module_constant():
    assert OpenAICompatAnsweringModel(model="alias").max_schema_retries == SCHEMA_MISS_MAX_RETRIES == 3


def test_respond_falls_back_to_tool_calls_after_exhausting_retries(monkeypatch):
    # 1 initial attempt + 3 retries (max_schema_retries default) all schema-miss,
    # then the tool-call fallback succeeds.
    model, pc, seen = _run_scripted(
        monkeypatch,
        [_payload(json.dumps(_INCOMPLETE_ANSWER))] * 4 + [_tool_call_payload(GOOD_ANSWER)],
    )
    assert pc.asserts_permission is True
    assert len(seen) == 5
    assert model.last_schema_retries == 4
    assert model.last_used_tool_call_fallback is True
    # the fallback request asks via tool/function-calling, not response_format
    assert "tools" in seen[-1] and "response_format" not in seen[-1]
    assert seen[-1]["tool_choice"]["function"]["name"] == "propose_change"


def test_respond_raises_after_exhausting_retries_and_fallback(monkeypatch):
    with pytest.raises(SchemaMissError):
        _run_scripted(
            monkeypatch,
            [_payload(json.dumps(_INCOMPLETE_ANSWER))] * 4 + [_payload(None, finish_reason="stop")],
        )


def test_respond_skips_fallback_when_disabled(monkeypatch):
    with pytest.raises(SchemaMissError, match="missing an expected"):
        _run_scripted(
            monkeypatch,
            [_payload(json.dumps(_INCOMPLETE_ANSWER))] * 4,
            use_tool_call_fallback=False,
        )
    # no 5th request: the fallback never fires when disabled
    assert len(_ScriptedGateway.seen_requests) == 4


def test_max_schema_retries_zero_means_a_single_response_format_attempt(monkeypatch):
    model, pc, seen = _run_scripted(
        monkeypatch,
        [_payload(json.dumps(_INCOMPLETE_ANSWER)), _tool_call_payload(GOOD_ANSWER)],
        max_schema_retries=0,
    )
    assert pc.asserts_permission is True
    assert len(seen) == 2  # 1 attempt (no retries) + 1 fallback
    assert model.last_schema_retries == 1
    assert model.last_used_tool_call_fallback is True


# --- context_window_tokens: probed from the gateway, not hardcoded ----------


class _ModelInfoGateway(BaseHTTPRequestHandler):
    """A mock gateway serving GET /v1/model/info (LiteLLM's model-info route)
    alongside the usual POST /chat/completions."""

    model_info_response: dict = {}
    model_info_status: int = 200
    get_requests: list = []

    def do_GET(self):  # noqa: N802
        _ModelInfoGateway.get_requests.append(
            {"path": self.path, "authorization": self.headers.get("Authorization")}
        )
        body = json.dumps(_ModelInfoGateway.model_info_response).encode("utf-8")
        self.send_response(_ModelInfoGateway.model_info_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        response = json.dumps(_payload(json.dumps(GOOD_ANSWER))).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *args):
        pass


def _serve_model_info(monkeypatch, response, status=200):
    _ModelInfoGateway.model_info_response = response
    _ModelInfoGateway.model_info_status = status
    _ModelInfoGateway.get_requests = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ModelInfoGateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    monkeypatch.setenv("LITELLM_BASE_URL", f"http://{host}:{port}")
    monkeypatch.setenv("LITELLM_API_KEY", "sk-test-virtual-key")
    return server


def test_context_window_tokens_probes_the_gateways_model_info(monkeypatch):
    server = _serve_model_info(monkeypatch, {
        "data": [
            {"model_name": "other-alias", "model_info": {"max_input_tokens": 999}},
            {"model_name": "my-alias", "model_info": {"max_input_tokens": 65536}},
        ]
    })
    try:
        model = OpenAICompatAnsweringModel(model="my-alias")
        assert model.context_window_tokens == 65536
        assert _ModelInfoGateway.get_requests[0]["path"] == "/v1/model/info"
        assert _ModelInfoGateway.get_requests[0]["authorization"] == "Bearer sk-test-virtual-key"
    finally:
        server.shutdown()
        server.server_close()


def test_context_window_tokens_caches_the_probe():
    calls = []

    class _Counting(OpenAICompatAnsweringModel):
        def _probe_context_window(self):
            calls.append(1)
            return 42

    model = _Counting(model="my-alias")
    assert model.context_window_tokens == 42
    assert model.context_window_tokens == 42
    assert len(calls) == 1  # probed once, then cached


def test_context_window_tokens_falls_back_when_the_gateway_lacks_model_info(monkeypatch):
    server = _serve_model_info(monkeypatch, {}, status=404)
    try:
        model = OpenAICompatAnsweringModel(model="my-alias")
        assert model.context_window_tokens == OpenAICompatAnsweringModel.DEFAULT_CONTEXT_WINDOW_TOKENS
    finally:
        server.shutdown()
        server.server_close()


def test_context_window_tokens_falls_back_when_the_alias_is_not_listed(monkeypatch):
    server = _serve_model_info(monkeypatch, {
        "data": [{"model_name": "some-other-alias", "model_info": {"max_input_tokens": 123}}]
    })
    try:
        model = OpenAICompatAnsweringModel(model="my-alias")
        assert model.context_window_tokens == OpenAICompatAnsweringModel.DEFAULT_CONTEXT_WINDOW_TOKENS
    finally:
        server.shutdown()
        server.server_close()


def test_context_window_tokens_explicit_override_skips_the_probe(monkeypatch):
    calls = []

    class _Counting(OpenAICompatAnsweringModel):
        def _probe_context_window(self):
            calls.append(1)
            return 999999

    model = _Counting(model="my-alias", context_window_tokens=7)
    assert model.context_window_tokens == 7
    assert calls == []  # never probed — the explicit value always wins


def test_context_window_tokens_explicit_none_disables_the_check(monkeypatch):
    model = OpenAICompatAnsweringModel(model="my-alias", context_window_tokens=None)
    assert model.context_window_tokens is None
