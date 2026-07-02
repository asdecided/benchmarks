"""browser-notes — a frozen sample app for the autonomousqa benchmark.

Serves the static notes board from ./static with the Python standard library
only. All behaviour lives in the page's vanilla JavaScript; the server never
holds state, so every fidelity re-run starts from a fresh page.

Frozen once published: behaviour changes only with a new benchmark app.
"""
import argparse
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

STATIC_DIR = Path(__file__).resolve().parent / "static"


class Handler(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:  # keep harness output clean
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the browser-notes sample app.")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    handler = partial(Handler, directory=str(STATIC_DIR))
    ThreadingHTTPServer((args.host, args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
