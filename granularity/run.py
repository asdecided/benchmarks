#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run both arms over a granularity corpus and emit the family scorecard.

    python granularity/run.py --corpus DIR [--out results.json]

Runs the ``artifacts`` and ``canon`` arms (see ``arms``) over ``DIR``'s
``queries.json``, scores each arm with the shared family scorer (P@1/3/5,
R@1/3/5, MRR macro-averaged, and full-returned-list supersession violations —
a ``must_not_return`` id ANYWHERE in the returned list is a violation), and
writes a scorecard whose ``metrics`` block is byte-identical across runs on an
unchanged corpus (ADR-066). A side-by-side table prints every metric in both
directions honestly, including any the canon arm wins.

Scoring is reused verbatim from the per-tool battery's ``harness.scoring``
(``score_retrieval_case`` — the same full-list negative window the family
uses); this driver only aggregates per arm. Nothing here imports the engine
(DG-ADR-0001).
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from harness.cases import K_VALUES  # noqa: E402
from harness.scoring import RetrievalResult, score_retrieval_case  # noqa: E402
from harness.cases import RetrievalCase  # noqa: E402

from arms import run_artifacts_arm, run_canon_arm  # noqa: E402

SCHEMA_VERSION = 1
_PRECISION = 6
_RETURNED_CAP = 20  # per_query stores a bounded prefix; scoring sees the full list


def _round(value: float) -> float:
    return round(value, _PRECISION)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _load_cases(corpus: Path) -> list[dict]:
    data = json.loads((corpus / "queries.json").read_text(encoding="utf-8"))
    return data["cases"]


def _to_case(raw: dict) -> RetrievalCase:
    return RetrievalCase(
        id=raw["id"],
        query=raw["query"],
        category=raw["class"],
        relevant=tuple(raw["must_return"]),
        must_not_return=tuple(raw.get("must_not_return", [])),
    )


def _score_arm(
    returned: dict[str, list[str]], cases: list[dict]
) -> dict[str, RetrievalResult]:
    return {
        raw["id"]: score_retrieval_case(returned.get(raw["id"], []), _to_case(raw))
        for raw in cases
    }


def _aggregate(results: dict[str, RetrievalResult]) -> dict[str, Any]:
    rows = list(results.values())
    overall: dict[str, Any] = {}
    for k in K_VALUES:
        overall[f"p_at_{k}"] = _round(_mean([r.precision[k] for r in rows]))
    for k in K_VALUES:
        overall[f"r_at_{k}"] = _round(_mean([r.recall[k] for r in rows]))
    overall["mrr"] = _round(_mean([r.reciprocal_rank for r in rows]))
    overall["supersession_violations"] = sum(len(r.violations) for r in rows)

    by_class: dict[str, Any] = {}
    groups: dict[str, list[RetrievalResult]] = {}
    for r in rows:
        groups.setdefault(r.case.category, []).append(r)
    for name in sorted(groups):
        members = groups[name]
        by_class[name] = {
            "p_at_1": _round(_mean([r.precision[1] for r in members])),
            "r_at_5": _round(_mean([r.recall[5] for r in members])),
            "mrr": _round(_mean([r.reciprocal_rank for r in members])),
            "supersession_violations": sum(len(r.violations) for r in members),
        }
    return {"overall": overall, "by_class": by_class}


def _engine_version() -> str:
    try:
        out = subprocess.run(
            ["rac", "--version"], capture_output=True, text=True, check=False
        )
        return (out.stdout or out.stderr).strip()
    except OSError:
        return "unavailable"


def _manifest(corpus: Path) -> dict[str, Any]:
    path = corpus / "manifest.json"
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _per_query(
    cases: list[dict], art: dict[str, RetrievalResult], can: dict[str, RetrievalResult]
) -> list[dict]:
    rows: list[dict] = []
    for raw in cases:
        cid = raw["id"]

        def arm_row(res: RetrievalResult) -> dict[str, Any]:
            row: dict[str, Any] = {"returned": res.returned[:_RETURNED_CAP]}
            for k in K_VALUES:
                row[f"p_at_{k}"] = _round(res.precision[k])
            for k in K_VALUES:
                row[f"r_at_{k}"] = _round(res.recall[k])
            row["mrr"] = _round(res.reciprocal_rank)
            row["violations"] = res.violations
            return row

        rows.append(
            {
                "id": cid,
                "class": raw["class"],
                "query": raw["query"],
                "must_return": raw["must_return"],
                "must_not_return": raw.get("must_not_return", []),
                "artifacts": arm_row(art[cid]),
                "canon": arm_row(can[cid]),
            }
        )
    return rows


def run(corpus: Path) -> dict[str, Any]:
    cases = _load_cases(corpus)
    artifacts_returned = run_artifacts_arm(corpus, cases)
    canon_returned = run_canon_arm(corpus, cases)

    art = _score_arm(artifacts_returned, cases)
    can = _score_arm(canon_returned, cases)
    manifest = _manifest(corpus)
    return {
        "schema_version": SCHEMA_VERSION,
        "metrics": {"artifacts": _aggregate(art), "canon": _aggregate(can)},
        "metadata": {
            "count": manifest.get("count"),
            "seed": manifest.get("seed"),
            "manifest_sha": manifest.get("sha256"),
            "engine_version": _engine_version(),
        },
        "per_query": _per_query(cases, art, can),
    }


# --- side-by-side table (both directions, honest) -------------------------

_TABLE_METRICS = (
    ("p_at_1", "P@1", True),
    ("p_at_3", "P@3", True),
    ("p_at_5", "P@5", True),
    ("r_at_1", "R@1", True),
    ("r_at_3", "R@3", True),
    ("r_at_5", "R@5", True),
    ("mrr", "MRR", True),
    ("supersession_violations", "supersession_violations", False),
)


def _print_table(scorecard: dict[str, Any]) -> None:
    art = scorecard["metrics"]["artifacts"]["overall"]
    can = scorecard["metrics"]["canon"]["overall"]
    width = max(len(label) for _key, label, _f in _TABLE_METRICS)
    header = f"{'metric':<{width}}  {'artifacts':>12}  {'canon':>12}  {'delta':>12}"
    print(header)
    print("-" * len(header))
    for key, label, is_float in _TABLE_METRICS:
        a, c = art[key], can[key]
        delta = a - c
        if is_float:
            print(f"{label:<{width}}  {a:>12.6f}  {c:>12.6f}  {delta:>+12.6f}")
        else:
            print(f"{label:<{width}}  {a:>12d}  {c:>12d}  {delta:>+12d}")
    print()
    print(
        "delta = artifacts - canon. For the metrics higher is better except "
        "supersession_violations, where lower is better (a negative delta "
        "means the artifacts arm leaked fewer superseded decisions)."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--corpus",
        type=Path,
        required=True,
        help="Granularity corpus directory (artifacts/ + canon/ + queries.json).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Scorecard JSON path (default: <corpus>/results.json).",
    )
    args = parser.parse_args(argv)
    if not args.corpus.is_dir():
        parser.error(f"corpus not found: {args.corpus}")
    if not (args.corpus / "queries.json").is_file():
        parser.error(
            f"queries.json missing under {args.corpus} — run build_queries.py first"
        )

    scorecard = run(args.corpus)
    out = args.out or (args.corpus / "results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(scorecard, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    count = scorecard["metadata"]["count"]
    print(
        f"scored {len(scorecard['per_query'])} cases over {count} artifacts -> {out}\n"
    )
    _print_table(scorecard)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
