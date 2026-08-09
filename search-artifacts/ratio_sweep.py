#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Diagnostic-only graph-floor sweep over the adversarial fixture category.

The gated scorecard always consumes production order verbatim. This script is
separate and non-gating: it uses production ``--explain`` components to answer
the tuning question, "which tested floor first protects every labelled case?"
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCHMARK_DIR.parent))

from harness.runner import RacRunner  # noqa: E402

DEFAULT_RATIOS = (0.75, 0.80, 0.85, 0.90, 0.95)
CASE_IDS = ("Q25", "Q26", "Q27", "Q28")


def _cases() -> list[dict]:
    payload = json.loads((BENCHMARK_DIR / "queries.json").read_text(encoding="utf-8"))
    wanted = set(CASE_IDS)
    return [case for case in payload["cases"] if case["id"] in wanted]


def _explained(query: str) -> list[dict]:
    result = RacRunner().run(
        "find",
        query,
        str(BENCHMARK_DIR / "corpus"),
        "--json",
        "--explain",
        "--no-cache",
    )
    if result.exit_code != 0:
        raise RuntimeError(result.stderr.strip() or f"decided find exited {result.exit_code}")
    return result.payload()["matches"]


def _rank_at_ratio(matches: list[dict], ratio: float) -> list[str]:
    strongest = max(match["evidence"]["components"]["bm25"] for match in matches)

    def scored(match: dict) -> tuple[float, str]:
        components = match["evidence"]["components"]
        score = 1.0 / (60 + components["lexical_rank"])
        if components["bm25"] >= strongest * ratio:
            score += 0.5 / (60 + components["graph_rank"])
        return (-round(score, 12), match["path"])

    return [match["id"] for match in sorted(matches, key=scored)]


def sweep(ratios: tuple[float, ...] = DEFAULT_RATIOS) -> dict:
    cases = _cases()
    explained = {case["id"]: _explained(case["query"]) for case in cases}
    rows: list[dict] = []
    for ratio in ratios:
        outcomes = []
        for case in cases:
            ranked = _rank_at_ratio(explained[case["id"]], ratio)
            outcomes.append(
                {
                    "id": case["id"],
                    "top": ranked[0],
                    "expected": case["relevant"][0],
                    "passed": ranked[0] == case["relevant"][0],
                }
            )
        passed = sum(outcome["passed"] for outcome in outcomes)
        rows.append(
            {
                "ratio": ratio,
                "p_at_1": round(passed / len(outcomes), 6),
                "cases": outcomes,
            }
        )
    passing = [row["ratio"] for row in rows if row["p_at_1"] == 1.0]
    return {
        "ratios": list(ratios),
        "minimum_passing_ratio": min(passing) if passing else None,
        "results": rows,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ratios",
        default=",".join(str(value) for value in DEFAULT_RATIOS),
        help="Comma-separated ratios (default: 0.75,0.80,0.85,0.90,0.95).",
    )
    args = parser.parse_args(argv)
    try:
        ratios = tuple(float(value) for value in args.ratios.split(","))
        if not ratios or any(value <= 0 or value > 1 for value in ratios):
            raise ValueError("ratios must be in (0, 1]")
        print(json.dumps(sweep(ratios), indent=2))
        return 0
    except (RuntimeError, ValueError) as exc:
        print(f"ratio-sweep: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
