"""cli-tally — man page server for the autonomousqa benchmark's CLI sample.

The product under verification is `tally.py`, a stateless CLI in this
directory. The drive still needs an HTTP entry point, so this server renders
the tool's man page — including the exact command to invoke it, with the
tool's absolute path on this machine — as the start URL.

Frozen once published: behaviour changes only with a new benchmark app.
"""
import argparse
import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

TALLY_PATH = Path(__file__).resolve().parent / "tally.py"

PAGE_TEMPLATE = """<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>tally(1)</title></head>
<body>
<main>
<h1>tally — count, sum, and sort numbers</h1>
<p>tally is a command-line tool. Run it with Python 3 from a terminal:</p>
<pre><code>python3 {tally_path} &lt;command&gt; [--json] &lt;numbers...&gt;</code></pre>
<h2>Commands</h2>
<ul>
  <li><code>sum 3 4 5</code> &mdash; prints the total, <code>12</code>.</li>
  <li><code>stats 3 4 5</code> &mdash; prints <code>count=3 min=3 max=5 sum=12</code>;
      with <code>--json</code> prints the same as one JSON object.</li>
  <li><code>sort 5 3 4</code> &mdash; prints <code>3 4 5</code>.</li>
  <li><code>--version</code> &mdash; prints <code>tally 1.0.0</code>.</li>
</ul>
<h2>Exit codes</h2>
<p><code>0</code> success; <code>2</code> usage error &mdash; unknown command, no
numbers, or a non-numeric token (reported on stderr as
<code>tally: 'x' is not a number</code>).</p>
</main>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = PAGE_TEMPLATE.format(tally_path=html.escape(str(TALLY_PATH))).encode()
        self.send_response(200)
        self.send_header("content-type", "text/html; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args) -> None:  # keep harness output clean
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve the tally man page.")
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--host", default="127.0.0.1")
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), Handler).serve_forever()


if __name__ == "__main__":
    main()
