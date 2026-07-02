"""api-ledger — a frozen sample app for the autonomousqa benchmark.

A small in-memory ledger exposed as a JSON API, served with the Python
standard library only. The root page is human-readable API documentation so
a browser-driving agent can discover the endpoints. State is per-process;
`POST /reset` returns the ledger to its starting state so verification flows
can be made re-run-safe.

Frozen once published: behaviour changes only with a new benchmark app.
"""
import argparse
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_LABEL_LENGTH = 64

_lock = threading.Lock()
_entries: list[dict] = []
_next_id = 1

DOCS_HTML = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>api-ledger</title></head>
<body>
<main>
<h1>api-ledger</h1>
<p>An in-memory ledger with a JSON API. All endpoints are on this origin.</p>
<h2>Endpoints</h2>
<ul>
  <li><code>GET /health</code> — service status; returns <code>{"status": "ok", "service": "api-ledger"}</code>.</li>
  <li><code>POST /entries</code> — record an entry. JSON body:
      <code>{"label": "coffee", "amount": -3}</code>.
      <code>label</code> is a non-empty string of at most 64 characters;
      <code>amount</code> is a non-zero integer (positive deposits, negative
      spends). Returns <code>201</code> with the stored entry, its assigned
      <code>id</code>, and the resulting <code>balance</code>.</li>
  <li><code>GET /entries</code> — list all entries with a <code>count</code>.</li>
  <li><code>GET /entries/&lt;id&gt;</code> — fetch one entry; unknown ids return
      <code>404</code> with error code <code>not_found</code>.</li>
  <li><code>GET /balance</code> — the sum of all recorded amounts.</li>
  <li><code>POST /reset</code> — test hook: clear the ledger and return
      <code>{"entries": 0, "balance": 0}</code>.</li>
</ul>
<p>Invalid input is rejected with <code>400</code> and a JSON error of the form
<code>{"error": {"code": "invalid_amount", "message": "..."}}</code>; codes are
<code>invalid_json</code>, <code>invalid_label</code>, <code>invalid_amount</code>.</p>
</main>
</body>
</html>
"""


def _reset() -> None:
    global _entries, _next_id
    with _lock:
        _entries = []
        _next_id = 1


class Handler(BaseHTTPRequestHandler):
    server_version = "api-ledger/1.0"

    def _send(self, status: int, payload, content_type: str = "application/json") -> None:
        body = payload.encode() if isinstance(payload, str) else json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _error(self, status: int, code: str, message: str) -> None:
        self._send(status, {"error": {"code": code, "message": message}})

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, DOCS_HTML, content_type="text/html; charset=utf-8")
        elif self.path == "/health":
            self._send(200, {"status": "ok", "service": "api-ledger"})
        elif self.path == "/entries":
            with _lock:
                entries = list(_entries)
            self._send(200, {"entries": entries, "count": len(entries)})
        elif re.fullmatch(r"/entries/\d+", self.path):
            entry_id = int(self.path.rsplit("/", 1)[1])
            with _lock:
                match = next((e for e in _entries if e["id"] == entry_id), None)
            if match is None:
                self._error(404, "not_found", f"no entry with id {entry_id}")
            else:
                self._send(200, match)
        elif self.path == "/balance":
            with _lock:
                balance = sum(e["amount"] for e in _entries)
            self._send(200, {"balance": balance})
        else:
            self._error(404, "not_found", f"unknown path {self.path}")

    def do_POST(self) -> None:
        global _next_id
        if self.path == "/reset":
            _reset()
            self._send(200, {"entries": 0, "balance": 0})
            return
        if self.path != "/entries":
            self._error(404, "not_found", f"unknown path {self.path}")
            return
        length = int(self.headers.get("content-length") or 0)
        try:
            payload = json.loads(self.rfile.read(length) or b"")
        except json.JSONDecodeError:
            self._error(400, "invalid_json", "the request body is not valid JSON")
            return
        if not isinstance(payload, dict):
            self._error(400, "invalid_json", "the request body must be a JSON object")
            return
        label = payload.get("label")
        amount = payload.get("amount")
        if not isinstance(label, str) or not label.strip() or len(label) > MAX_LABEL_LENGTH:
            self._error(400, "invalid_label",
                        f"label must be a non-empty string of at most {MAX_LABEL_LENGTH} characters")
            return
        if isinstance(amount, bool) or not isinstance(amount, int) or amount == 0:
            self._error(400, "invalid_amount", "amount must be a non-zero integer")
            return
        with _lock:
            entry = {"id": _next_id, "label": label, "amount": amount}
            _next_id += 1
            _entries.append(entry)
            balance = sum(e["amount"] for e in _entries)
        self._send(201, {**entry, "balance": balance})

    def log_message(self, *args) -> None:  # keep harness output clean
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the api-ledger sample app.")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
