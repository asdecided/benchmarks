#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Fetch the GitChameleon 2.0 problem set (fetch-on-demand; never committed).

Downloads all rows of the upstream dataset — `cabbage972/GitChameleon-2.0`
(MIT), the dataset behind GitChameleon 2.0 (arXiv:2507.12367; upstream code
Apache-2.0 at github.com/mrcabbage972/GitChameleonBenchmark) — from the raw
JSONL at an exact Hugging Face commit, stdlib only. Writes:

- ``dataset/problems.json`` — the rows, exactly as served.
- ``dataset/provenance.json`` — the dataset revision, row count, retrieval
  time, and a sha256 over the normalized rows, so every downstream artifact
  can name the exact upstream pin it was built from.

The dataset directory is gitignored: our repository carries provenance, not a
vendored copy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import quote

DATASET = "cabbage972/GitChameleon-2.0"
CONFIG = "problems"
SPLIT = "train"
OUT_DIR = Path(__file__).resolve().parent / "dataset"


def _get_json(url: str) -> dict:
    with urllib.request.urlopen(url) as response:
        return json.load(response)


def fetch_rows(revision: str) -> list[dict]:
    """Fetch the immutable raw JSONL at one exact Hub commit."""
    dataset_path = quote(DATASET, safe="/")
    revision_path = quote(revision, safe="")
    url = (
        f"https://huggingface.co/datasets/{dataset_path}/resolve/"
        f"{revision_path}/dataset.jsonl"
    )
    with urllib.request.urlopen(url) as response:
        return [
            json.loads(line)
            for line in response.read().decode("utf-8").splitlines()
            if line.strip()
        ]


def dataset_revision() -> str:
    # Hugging Face's repository endpoint treats owner/name as path segments;
    # percent-encoding the slash returns HTTP 400.
    payload = _get_json(
        f"https://huggingface.co/api/datasets/{quote(DATASET, safe='/')}"
    )
    return str(payload.get("sha", "unknown"))


def rows_hash(rows: list[dict]) -> str:
    canonical = json.dumps(
        rows, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--revision",
        default=None,
        help="exact Hugging Face dataset commit (default: resolve current HEAD once)",
    )
    args = parser.parse_args(argv)
    revision = args.revision or dataset_revision()
    if revision == "unknown":
        print("fetch_dataset: upstream returned no dataset revision", file=sys.stderr)
        return 1
    rows = fetch_rows(revision)
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
        "revision": revision,
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
