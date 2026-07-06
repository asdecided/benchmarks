#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Deterministic query set for the granularity member, from the same seed.

    python granularity/build_queries.py --count N --out DIR [--seed 42]

Writes ``DIR/queries.json`` — ~60 cases at 1k, ~100 at 10k/100k — re-derived
from the ``_model`` records, so a query knows which decision is live and which
are its superseded ancestors without reading the corpus. Case shape (ADR-097
family form)::

    {"id", "class": "topic"|"supersession"|"related",
     "query", "must_return": [live decision id],
     "must_not_return": [superseded ancestor ids...]}

Three classes:

- ``topic`` — a standalone live decision queried by its own topic terms; no
  superseded negatives. A plain retrieval-quality comparison (the canon arm can
  win it, and the scorecard reports that honestly).
- ``supersession`` — the heart. The query is built from a chain's shared topic
  terms, so it lexically matches BOTH the superseded ancestors AND the live
  head. Only liveness knowledge picks the head; the superseded ancestors are
  the hard negatives.
- ``related`` — a live chain head reached through a requirement that references
  it, queried by that requirement's (head-derived) terms; the head's superseded
  ancestors are the negatives. A second, independently seeded population of the
  supersession-defense case.

The artifacts arm answers ``supersession`` / ``related`` with the typed
live-decision tool (``find_decisions``), which the per-file model's
``Superseded`` status enables; the canon arm has no such filter — that is the
measured difference. Stdlib only; never imports the engine (DG-ADR-0001).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _model import (  # noqa: E402
    chain_info,
    decision_count,
    decision_record,
    requirement_record,
)

# Case-count ladder and class split (roadmap: ~60 at 1k, ~100 at 10k/100k).
SMALL_TOTAL = 60
LARGE_TOTAL = 100
SMALL_THRESHOLD = 1000
CLASS_SPLIT = (("topic", 0.40), ("supersession", 0.35), ("related", 0.25))


def _totals(count: int) -> dict[str, int]:
    n = SMALL_TOTAL if count <= SMALL_THRESHOLD else LARGE_TOTAL
    totals = {name: round(n * share) for name, share in CLASS_SPLIT[:-1]}
    last = CLASS_SPLIT[-1][0]
    totals[last] = n - sum(totals.values())
    return totals


def _stride(candidates: list, want: int) -> list:
    """A deterministic, spread-out subset of ``candidates`` of size ``want``.

    A fixed stride (not a shuffle) keeps selection stable and samples the whole
    id range rather than clustering at the front.
    """
    if want <= 0 or not candidates:
        return []
    if want >= len(candidates):
        return candidates
    step = len(candidates) / want
    return [candidates[int(i * step)] for i in range(want)]


def _query(terms: tuple[str, ...]) -> str:
    """The query string for a case — the artifact's distinctive topic terms."""
    return " ".join(terms)


def build_cases(count: int, seed: int) -> list[dict]:
    n_decisions = decision_count(count)
    totals = _totals(count)

    topic_c: list[dict] = []
    supersession_c: list[dict] = []
    for index in range(n_decisions):
        info = chain_info(index, n_decisions)
        if index != info.head:
            continue  # only the live head is ever a must_return target
        dec = decision_record(index, seed, n_decisions)
        if dec.ancestor_ids:  # a chain head with superseded ancestors
            supersession_c.append(
                {
                    "class": "supersession",
                    "query": _query(dec.terms),
                    "must_return": [dec.id],
                    "must_not_return": list(dec.ancestor_ids),
                }
            )
        else:  # a standalone live decision
            topic_c.append(
                {
                    "class": "topic",
                    "query": _query(dec.terms),
                    "must_return": [dec.id],
                    "must_not_return": [],
                }
            )

    related_c: list[dict] = []
    for index in range(n_decisions, count):
        req = requirement_record(index, seed, n_decisions)
        if req.head_ref and req.head_ancestors:
            related_c.append(
                {
                    "class": "related",
                    "query": _query(req.terms),
                    "must_return": [req.head_ref],
                    "must_not_return": list(req.head_ancestors),
                }
            )

    selected = (
        _stride(topic_c, totals["topic"])
        + _stride(supersession_c, totals["supersession"])
        + _stride(related_c, totals["related"])
    )
    cases: list[dict] = []
    for i, case in enumerate(selected):
        cases.append({"id": f"G{i:03d}", **case})
    return cases


def build_query_set(count: int, seed: int) -> dict:
    return {
        "schema_version": 1,
        "count": count,
        "seed": seed,
        "cases": build_cases(count, seed),
    }


def write_queries(out: Path, count: int, seed: int) -> Path:
    payload = build_query_set(count, seed)
    path = out / "queries.json"
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        help="Corpus size the queries target (must match the "
        "corpus built at the same seed).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Corpus directory to write queries.json into.",
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Deterministic seed (default: 42)."
    )
    args = parser.parse_args(argv)
    if args.count < 0:
        parser.error("--count must be non-negative")

    path = write_queries(args.out, args.count, args.seed)
    payload = json.loads(path.read_text(encoding="utf-8"))
    by_class: dict[str, int] = {}
    for case in payload["cases"]:
        by_class[case["class"]] = by_class.get(case["class"], 0) + 1
    mix = ", ".join(f"{k}={v}" for k, v in sorted(by_class.items()))
    print(f"wrote {len(payload['cases'])} cases -> {path}")
    print(f"  classes: {mix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
