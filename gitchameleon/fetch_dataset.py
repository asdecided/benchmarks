#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch the GitChameleon 2.0 problem set (fetch-on-demand; never committed).

Downloads all rows of the upstream dataset — `cabbage972/GitChameleon-2.0`
(MIT), the dataset behind GitChameleon 2.0 (arXiv:2507.12367; upstream code
Apache-2.0 at github.com/mrcabbage972/GitChameleonBenchmark) — via the
HuggingFace datasets-server API, stdlib only. Writes:

- ``dataset/problems.json`` — the rows, exactly as served.
- ``dataset/provenance.json`` — the dataset revision, row count, retrieval
  time, and a sha256 over the normalized rows, so every downstream artifact
  can name the exact upstream pin it was built from.

The dataset directory is gitignored: our repository carries provenance, not a
vendored copy.
"""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

DATASET = "cabbage972/GitChameleon-2.0"
CONFIG = "problems"
SPLIT = "train"
PAGE = 100
BASE = "https://datasets-server.huggingface.co"
OUT_DIR = Path(__file__).resolve().parent / "dataset"


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url) as response:
        return json.load(response)


def fetch_rows() -> list[dict]:
    rows: list[dict] = []
    offset = 0
    while True:
        payload = _get_json(
            f"{BASE}/rows?dataset={DATASET}&config={CONFIG}&split={SPLIT}"
            f"&offset={offset}&length={PAGE}"
        )
        batch = [entry["row"] for entry in payload["rows"]]
        if not batch:
            break
        rows.extend(batch)
        offset += len(batch)
        if len(batch) < PAGE:
            break
    return rows


def dataset_revision() -> str:
    payload = _get_json(f"https://huggingface.co/api/datasets/{DATASET.replace('/', '%2F')}")
    return str(payload.get("sha", "unknown"))


def rows_hash(rows: list[dict]) -> str:
    canonical = json.dumps(rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main() -> int:
    rows = fetch_rows()
    if not rows:
        print("fetch_dataset: upstream returned no rows", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "problems.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    provenance = {
        "dataset": DATASET,
        "config": CONFIG,
        "split": SPLIT,
        "license": "MIT",
        "revision": dataset_revision(),
        "n_rows": len(rows),
        "rows_hash": rows_hash(rows),
        "fetched_at": datetime.now(UTC).isoformat(),
    }
    (OUT_DIR / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    print(f"fetched {len(rows)} rows at revision {provenance['revision']}")
    print(f"-> {OUT_DIR / 'problems.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
