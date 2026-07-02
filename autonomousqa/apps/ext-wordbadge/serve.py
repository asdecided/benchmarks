"""ext-wordbadge — target-page server for the autonomousqa benchmark's
browser-extension sample.

The product under verification is the unpacked MV3 extension in ./extension;
these static pages are the fixed content it badges. Served with the Python
standard library only.

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
    parser = argparse.ArgumentParser(description="Serve the wordbadge target pages.")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    handler = partial(Handler, directory=str(STATIC_DIR))
    ThreadingHTTPServer((args.host, args.port), handler).serve_forever()


if __name__ == "__main__":
    main()
