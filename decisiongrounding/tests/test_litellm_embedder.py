"""Cover the LiteLLM `/embeddings` backend for `naive_rag`.

Same offline-mock-gateway pattern as test_litellm_backend.py: a stdlib
http.server mock stands in for the LiteLLM proxy's OpenAI-shape `/embeddings`
surface, so `naive_rag` can run behind a corporate gateway with zero
HuggingFace/Voyage dependency (e.g. `litellm:text-embedding-3-large`).
"""

from __future__ import annotations

import json
import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from providers import LiteLLMEmbedder, make_embedder
from providers.embedding import _l2_normalize


# --- factory routing ---------------------------------------------------------


def test_make_embedder_routes_litellm_spec():
    e = make_embedder("litellm:text-embedding-3-large")
    assert isinstance(e, LiteLLMEmbedder)
    assert e.model == "text-embedding-3-large"
    assert e.name == "litellm:text-embedding-3-large"


def test_make_embedder_litellm_defaults_model():
    e = make_embedder("litellm")
    assert isinstance(e, LiteLLMEmbedder)
    assert e.model == "text-embedding-3-large"


def test_make_embedder_constructs_litellm_lazily():
    # Constructing must not require network or credentials (lazy, like Voyage).
    e = LiteLLMEmbedder("text-embedding-3-large")
    assert e.dim == 0  # probed on first embed()


def test_litellm_embedder_requires_gateway_configuration(monkeypatch):
    monkeypatch.delenv("LITELLM_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    e = LiteLLMEmbedder("text-embedding-3-large")
    with pytest.raises(RuntimeError, match="LITELLM_BASE_URL"):
        e.embed("hello")


# --- full round-trip against a localhost mock gateway ------------------------


class _MockEmbeddingsGateway(BaseHTTPRequestHandler):
    """A minimal /embeddings endpoint recording the request it saw."""

    seen: dict = {}
    vector = [0.1, 0.2, 0.3, 0.4]

    def do_POST(self):  # noqa: N802 (http.server naming)
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        _MockEmbeddingsGateway.seen = {
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "body": body,
        }
        response = json.dumps(
            {"data": [{"embedding": _MockEmbeddingsGateway.vector, "index": 0}],
             "model": body["model"]}
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *args):  # silence request logging in test output
        pass


def test_embed_round_trip_via_mock_gateway(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockEmbeddingsGateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        monkeypatch.setenv("LITELLM_BASE_URL", f"http://{host}:{port}")
        monkeypatch.setenv("LITELLM_API_KEY", "sk-test-virtual-key")

        e = make_embedder("litellm:text-embedding-3-large")
        vec = e.embed("some grounding text")

        assert e.dim == 4
        assert math.isclose(sum(v * v for v in vec), 1.0, rel_tol=1e-6)
        assert vec == pytest.approx(_l2_normalize(_MockEmbeddingsGateway.vector))
        assert _MockEmbeddingsGateway.seen["path"] == "/embeddings"
        assert _MockEmbeddingsGateway.seen["authorization"] == "Bearer sk-test-virtual-key"
        assert _MockEmbeddingsGateway.seen["body"]["model"] == "text-embedding-3-large"
        assert _MockEmbeddingsGateway.seen["body"]["input"] == "some grounding text"
    finally:
        server.shutdown()
        server.server_close()


def test_embed_ignores_input_type_role(monkeypatch):
    # OpenAI-shape /embeddings has no query/document role; the call must not
    # fail whether or not a role is passed (mirrors LocalDeterministicEmbedder).
    server = ThreadingHTTPServer(("127.0.0.1", 0), _MockEmbeddingsGateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        monkeypatch.setenv("LITELLM_BASE_URL", f"http://{host}:{port}")
        monkeypatch.setenv("LITELLM_API_KEY", "sk-test-virtual-key")
        e = make_embedder("litellm:text-embedding-3-large")
        assert e.embed("x", input_type="query") == e.embed("x", input_type="document")
    finally:
        server.shutdown()
        server.server_close()


class _EmptyDataGateway(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", 0))
        self.rfile.read(length)
        response = json.dumps({"data": []}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *args):
        pass


def test_embed_fails_loudly_on_empty_data(monkeypatch):
    server = ThreadingHTTPServer(("127.0.0.1", 0), _EmptyDataGateway)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        monkeypatch.setenv("LITELLM_BASE_URL", f"http://{host}:{port}")
        monkeypatch.setenv("LITELLM_API_KEY", "sk-test-virtual-key")
        e = make_embedder("litellm:text-embedding-3-large")
        with pytest.raises(RuntimeError, match="no data"):
            e.embed("x")
    finally:
        server.shutdown()
        server.server_close()
