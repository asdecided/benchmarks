"""The frozen apps behave as their corpora claim (server-side modalities).

These run the real sample-app servers on local ports — stdlib only, no
browser, no agent — so the seeded acceptance criteria stay true as long as
CI is green.
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request

import pytest

from runner.apps import APPS_ROOT, AppServer, load_manifest

TALLY = APPS_ROOT / "cli-tally" / "tally.py"


@pytest.fixture(scope="module")
def ledger():
    with AppServer(load_manifest(APPS_ROOT / "api-ledger")) as server:
        yield server


def get(url: str):
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def post(url: str, payload=None):
    data = json.dumps(payload).encode() if payload is not None else b""
    request = urllib.request.Request(
        url, data=data, headers={"content-type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as err:
        return err.code, json.loads(err.read())


def test_ledger_health(ledger):
    assert get(ledger.base_url + "/health") == (200, {"status": "ok", "service": "api-ledger"})


def test_ledger_record_and_reject(ledger):
    status, body = post(ledger.base_url + "/entries", {"label": "coffee", "amount": -3})
    assert status == 201 and body["label"] == "coffee" and body["amount"] == -3

    status, body = post(ledger.base_url + "/entries", {"label": "oops", "amount": 0})
    assert status == 400 and body["error"]["code"] == "invalid_amount"

    status, body = post(ledger.base_url + "/entries", {"label": "", "amount": 3})
    assert status == 400 and body["error"]["code"] == "invalid_label"


def test_ledger_unknown_entry_and_balance(ledger):
    assert get(ledger.base_url + "/entries/999999")[0] == 404
    assert post(ledger.base_url + "/reset")[1] == {"entries": 0, "balance": 0}
    post(ledger.base_url + "/entries", {"label": "pay", "amount": 10})
    post(ledger.base_url + "/entries", {"label": "snack", "amount": -3})
    assert get(ledger.base_url + "/balance") == (200, {"balance": 7})


def tally(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TALLY), *args],
                          capture_output=True, text=True)


def test_tally_version_sum_stats():
    assert tally("--version").stdout == "tally 1.0.0\n"
    assert tally("sum", "3", "4", "5").stdout == "12\n"
    assert tally("stats", "3", "4", "5").stdout == "count=3 min=3 max=5 sum=12\n"
    assert tally("stats", "--json", "3", "4", "5").stdout == \
        '{"count": 3, "min": 3, "max": 5, "sum": 12}\n'


def test_tally_rejects_non_numeric():
    result = tally("sum", "3", "x")
    assert result.returncode == 2
    assert "tally: 'x' is not a number" in result.stderr


def test_wordbadge_page_counts_match_the_corpus():
    # The corpus promises exact counts (60/24/12) using the extension's
    # tokenizer: whitespace-split tokens containing a letter or digit.
    import re
    from html.parser import HTMLParser

    class MainText(HTMLParser):
        def __init__(self):
            super().__init__()
            self.depth = 0
            self.chunks = []

        def handle_starttag(self, tag, attrs):
            if tag == "main":
                self.depth += 1

        def handle_endtag(self, tag):
            if tag == "main":
                self.depth -= 1

        def handle_data(self, data):
            if self.depth:
                self.chunks.append(data)

    expected = {"article": 60, "poem": 24, "decoys": 12}
    for page, count in expected.items():
        parser = MainText()
        parser.feed((APPS_ROOT / "ext-wordbadge" / "static" / f"{page}.html").read_text())
        tokens = [t for t in re.split(r"\s+", " ".join(parser.chunks))
                  if re.search(r"[A-Za-z0-9]", t)]
        assert len(tokens) == count, f"{page}.html holds {len(tokens)} words, corpus says {count}"
