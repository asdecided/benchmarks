"""The model seam: an OpenAI-compatible proxy that meters or scripts.

The published BYOK contract of the reference agent lets any OpenAI-compatible
endpoint serve the drive (`OPENAI_BASE_URL`). The harness points the agent at
this local proxy, which runs in one of two modes:

- **forward** — relay each `/chat/completions` call to the real upstream
  provider and record the `usage` block from every response. This is how the
  benchmark measures tokens in/out for any agent and any provider without
  touching agent internals.
- **scripted** — serve a canned tool-call sequence from an app's flow file:
  the deterministic stand-in that lets CI exercise the whole loop (drive →
  compile → fidelity → score) with no key and no token spend. Scripted runs
  are harness illustrations, never benchmark results, and are marked as such
  in the record.

Stdlib only; one thread per proxy.
"""
from __future__ import annotations

import json
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

DEFAULT_UPSTREAM = "https://api.openai.com/v1"


def load_flow(flow_path: Path, substitutions: dict[str, str]) -> list[list[dict]]:
    """Load a scripted flow and substitute placeholders like {base_url}."""
    text = flow_path.read_text()
    for key, value in substitutions.items():
        text = text.replace("{" + key + "}", value)
    return json.loads(text)["turns"]


def _estimate_tokens(text: str) -> int:
    """A deterministic stand-in count for scripted mode (chars / 4)."""
    return max(1, len(text) // 4)


class ModelProxy:
    """One local OpenAI-compatible endpoint; collects a usage ledger."""

    def __init__(self, mode: str, *, flow: list[list[dict]] | None = None,
                 upstream_base_url: str | None = None, upstream_api_key: str | None = None):
        if mode not in ("forward", "scripted"):
            raise ValueError(f"unknown proxy mode '{mode}'")
        if mode == "scripted" and flow is None:
            raise ValueError("scripted mode needs a flow")
        self.mode = mode
        self.flow = flow or []
        self.upstream_base_url = (upstream_base_url or DEFAULT_UPSTREAM).rstrip("/")
        self.upstream_api_key = upstream_api_key
        self.usage: list[dict] = []
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.port: int | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def usage_totals(self) -> dict:
        with self._lock:
            entries = list(self.usage)
        return {
            "requests": len(entries),
            "prompt_tokens": sum(e.get("prompt_tokens", 0) for e in entries),
            "completion_tokens": sum(e.get("completion_tokens", 0) for e in entries),
            "estimated": self.mode == "scripted",
        }

    def _record_usage(self, usage: dict) -> None:
        with self._lock:
            self.usage.append(usage)

    def _scripted_response(self, payload: dict) -> dict:
        turn = sum(1 for m in payload.get("messages", []) if m.get("role") == "assistant")
        if turn < len(self.flow):
            calls = [
                {
                    "id": f"scripted_{turn}_{i}",
                    "type": "function",
                    "function": {"name": c["name"], "arguments": json.dumps(c["arguments"])},
                }
                for i, c in enumerate(self.flow[turn])
            ]
            message = {"role": "assistant", "content": None, "tool_calls": calls}
        else:
            message = {"role": "assistant", "content": "The scripted flow is complete."}
        usage = {
            "prompt_tokens": _estimate_tokens(json.dumps(payload.get("messages", []))),
            "completion_tokens": _estimate_tokens(json.dumps(message)),
        }
        self._record_usage(usage)
        return {
            "id": "scripted-proxy",
            "object": "chat.completion",
            "model": payload.get("model", "scripted"),
            "choices": [{"index": 0, "message": message, "finish_reason": "stop"}],
            "usage": usage,
        }

    def _forward_response(self, payload: dict) -> tuple[int, dict]:
        request = urllib.request.Request(
            f"{self.upstream_base_url}/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "content-type": "application/json",
                **({"authorization": f"Bearer {self.upstream_api_key}"}
                   if self.upstream_api_key else {}),
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                body = json.loads(response.read())
                status = response.status
        except urllib.error.HTTPError as err:
            return err.code, json.loads(err.read() or b"{}")
        usage = body.get("usage") or {}
        self._record_usage({
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
        })
        return status, body

    def start(self) -> None:
        proxy = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                length = int(self.headers.get("content-length") or 0)
                try:
                    payload = json.loads(self.rfile.read(length) or b"{}")
                except json.JSONDecodeError:
                    self._send(400, {"error": {"message": "invalid JSON"}})
                    return
                if not self.path.endswith("/chat/completions"):
                    self._send(404, {"error": {"message": f"unknown path {self.path}"}})
                    return
                if proxy.mode == "scripted":
                    self._send(200, proxy._scripted_response(payload))
                else:
                    status, body = proxy._forward_response(payload)
                    self._send(status, body)

            def _send(self, status: int, body: dict) -> None:
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("content-type", "application/json")
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None:
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        self._thread = None

    def __enter__(self) -> "ModelProxy":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()
