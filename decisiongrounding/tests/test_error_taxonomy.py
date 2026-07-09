"""error_kind(): type-based classification of cell failures, and the typed
GatewayHTTPError raised by the litellm transport."""

import io
import urllib.error

import pytest

from providers.answering import (
    GatewayHTTPError,
    OpenAICompatAnsweringModel,
    SchemaMissError,
    error_kind,
)
from providers.base import ContextWindowExceededError


def test_error_kind_classifies_by_type():
    assert error_kind(ContextWindowExceededError("x", token_estimate=1)) == (
        "context_window_exceeded"
    )
    assert error_kind(SchemaMissError("bad json")) == "schema"
    assert error_kind(GatewayHTTPError("HTTP 403", status=403)) == "gateway"
    assert error_kind(urllib.error.URLError("refused")) == "transport"
    assert error_kind(TimeoutError("slow")) == "transport"
    assert error_kind(ConnectionError("reset")) == "transport"
    assert error_kind(RuntimeError("anything else")) == "error"
    assert error_kind(ValueError("misc")) == "error"


def test_error_kind_classifies_anthropic_errors_as_transport():
    anthropic = pytest.importorskip("anthropic")
    exc = anthropic.APIConnectionError(request=None)
    assert error_kind(exc) == "transport"


def test_post_raises_gateway_http_error_still_a_runtime_error(monkeypatch):
    model = OpenAICompatAnsweringModel(model="alias")
    monkeypatch.setenv("LITELLM_BASE_URL", "http://gateway.test")
    monkeypatch.setenv("LITELLM_API_KEY", "k")

    def reject(request, timeout):
        raise urllib.error.HTTPError(
            "http://gateway.test", 403, "Forbidden", {}, io.BytesIO(b"policy: no")
        )

    monkeypatch.setattr("urllib.request.urlopen", reject)
    with pytest.raises(GatewayHTTPError) as ei:
        model._post({"model": "alias"})
    assert isinstance(ei.value, RuntimeError)  # existing call sites unaffected
    assert ei.value.status == 403
    # Message text is load-bearing for _reraise_if_context_length and tests.
    assert str(ei.value).startswith("litellm gateway returned HTTP 403")
    assert error_kind(ei.value) == "gateway"
