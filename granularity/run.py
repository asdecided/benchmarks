#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Run all four arms over a granularity corpus and emit the family scorecard.

    python granularity/run.py --corpus DIR [--out results.json]

Runs the four arms (see ``arms``) over ``DIR``'s ``queries.json``, scores each
with the shared family scorer (P@1/3/5, R@1/3/5, MRR macro-averaged, and
full-returned-list supersession violations — a ``must_not_return`` id ANYWHERE
in the returned list is a violation), and writes a scorecard whose ``metrics``
block is byte-identical across runs on an unchanged corpus (ADR-066).

The four arms and the three paired comparisons they exist to isolate:

- ``bm25-artifacts`` vs ``canon`` — pure granularity, one identical ranker.
- ``canon-status`` vs ``canon`` — what a status-aware parser recovers.
- ``artifacts`` (engine) vs ``bm25-artifacts`` — what the typed engine adds
  beyond granularity (field weights, graph, prefix, liveness).

Every metric prints for all four arms, and every comparison prints per class in
both directions honestly, including any the monolithic arm wins. Metrics also
break out per selectivity (``named`` vs ``topical``) so the size-independent
series the coined vocabulary provides is separable from the saturating one.

Scoring is reused verbatim from the per-tool battery's ``harness.scoring``
(``score_retrieval_case``). Nothing here imports the engine (DG-ADR-0001).
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

from _model import MODEL_VERSION  # noqa: E402
from arms import (  # noqa: E402
    run_artifacts_arm,
    run_bm25_artifacts_arm,
    run_canon_arm,
    run_canon_status_arm,
)

SCHEMA_VERSION = 1
_PRECISION = 6
_RETURNED_CAP = 20  # per_query stores a bounded prefix; scoring sees the full list

# Arm order is stable everywhere it is printed or serialised.
ARMS = ("artifacts", "bm25-artifacts", "canon", "canon-status")
_ARM_RUNNERS = {
    "artifacts": run_artifacts_arm,
    "bm25-artifacts": run_bm25_artifacts_arm,
    "canon": run_canon_arm,
    "canon-status": run_canon_status_arm,
}

# (higher, lower, label) — each isolates exactly one variable.
COMPARISONS = (
    ("bm25-artifacts", "canon", "pure granularity (shared ranker)"),
    ("canon-status", "canon", "status-parser recovery"),
    ("artifacts", "bm25-artifacts", "typed-engine value"),
)

# Overall metric keys, in print order, with their float/int and direction flags.
_METRICS = (
    ("p_at_1", "P@1", True, True),
    ("p_at_3", "P@3", True, True),
    ("p_at_5", "P@5", True, True),
    ("r_at_1", "R@1", True, True),
    ("r_at_3", "R@3", True, True),
    ("r_at_5", "R@5", True, True),
    ("mrr", "MRR", True, True),
    ("supersession_violations", "supersession_violations", False, False),
)


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


# --- aggregation ----------------------------------------------------------


def _overall(rows: list[RetrievalResult]) -> dict[str, Any]:
    overall: dict[str, Any] = {}
    for k in K_VALUES:
        overall[f"p_at_{k}"] = _round(_mean([r.precision[k] for r in rows]))
    for k in K_VALUES:
        overall[f"r_at_{k}"] = _round(_mean([r.recall[k] for r in rows]))
    overall["mrr"] = _round(_mean([r.reciprocal_rank for r in rows]))
    overall["supersession_violations"] = sum(len(r.violations) for r in rows)
    return overall


def _group_metrics(rows: list[RetrievalResult]) -> dict[str, Any]:
    return {
        "p_at_1": _round(_mean([r.precision[1] for r in rows])),
        "r_at_5": _round(_mean([r.recall[5] for r in rows])),
        "mrr": _round(_mean([r.reciprocal_rank for r in rows])),
        "supersession_violations": sum(len(r.violations) for r in rows),
    }


def _aggregate(
    results: dict[str, RetrievalResult], selectivity_by_id: dict[str, str]
) -> dict[str, Any]:
    rows = list(results.values())
    by_class: dict[str, list[RetrievalResult]] = {}
    by_sel: dict[str, list[RetrievalResult]] = {}
    for r in rows:
        by_class.setdefault(r.case.category, []).append(r)
        by_sel.setdefault(selectivity_by_id.get(r.case.id, "topical"), []).append(r)
    return {
        "overall": _overall(rows),
        "by_class": {name: _group_metrics(by_class[name]) for name in sorted(by_class)},
        "by_selectivity": {
            name: _group_metrics(by_sel[name]) for name in sorted(by_sel)
        },
    }


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
    cases: list[dict], scored: dict[str, dict[str, RetrievalResult]]
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

        row: dict[str, Any] = {
            "id": cid,
            "class": raw["class"],
            "selectivity": raw.get("selectivity", "topical"),
            "query": raw["query"],
            "must_return": raw["must_return"],
            "must_not_return": raw.get("must_not_return", []),
        }
        for arm in ARMS:
            row[arm] = arm_row(scored[arm][cid])
        rows.append(row)
    return rows


def run(corpus: Path) -> dict[str, Any]:
    cases = _load_cases(corpus)
    selectivity_by_id = {c["id"]: c.get("selectivity", "topical") for c in cases}

    scored: dict[str, dict[str, RetrievalResult]] = {}
    for arm in ARMS:
        returned = _ARM_RUNNERS[arm](corpus, cases)
        scored[arm] = _score_arm(returned, cases)

    manifest = _manifest(corpus)
    return {
        "schema_version": SCHEMA_VERSION,
        "model_version": manifest.get("model_version", MODEL_VERSION),
        "metrics": {arm: _aggregate(scored[arm], selectivity_by_id) for arm in ARMS},
        "metadata": {
            "count": manifest.get("count"),
            "seed": manifest.get("seed"),
            "model_version": manifest.get("model_version", MODEL_VERSION),
            "manifest_sha": manifest.get("sha256"),
            "engine_version": _engine_version(),
        },
        "per_query": _per_query(cases, scored),
    }


# --- single-seed tables ---------------------------------------------------


def _fmt(value: Any, is_float: bool) -> str:
    return f"{float(value):>12.6f}" if is_float else f"{int(value):>12d}"


def _print_arms_table(scorecard: dict[str, Any]) -> None:
    overalls = {arm: scorecard["metrics"][arm]["overall"] for arm in ARMS}
    label_w = max(len(label) for _k, label, _f, _h in _METRICS)
    header = f"{'metric':<{label_w}}" + "".join(f"  {arm:>14}" for arm in ARMS)
    print("Four arms — overall")
    print(header)
    print("-" * len(header))
    for key, label, is_float, _hib in _METRICS:
        cells = "".join(f"  {_fmt(overalls[arm][key], is_float):>14}" for arm in ARMS)
        print(f"{label:<{label_w}}{cells}")
    print()


def _print_comparisons(scorecard: dict[str, Any]) -> None:
    print("Paired comparisons — delta = higher_arm - lower_arm, per class")
    for high, low, label in COMPARISONS:
        print(f"\n[{high}] vs [{low}] — {label}")
        classes = sorted(scorecard["metrics"][high]["by_class"])
        cmp_metrics = ("p_at_1", "r_at_5", "mrr", "supersession_violations")
        head = f"  {'class':<14}" + "".join(f"  {m:>26}" for m in cmp_metrics)
        print(head)
        for cls in classes:
            hi = scorecard["metrics"][high]["by_class"][cls]
            lo = scorecard["metrics"][low]["by_class"][cls]
            cells = ""
            for m in cmp_metrics:
                is_float = m != "supersession_violations"
                a, b = hi[m], lo[m]
                if is_float:
                    cell = f"{a:.4f}/{b:.4f} d{a - b:+.4f}"
                else:
                    cell = f"{int(a)}/{int(b)} d{int(a) - int(b):+d}"
                cells += f"  {cell:>26}"
            print(f"  {cls:<14}{cells}")
    print(
        "\n(each cell is higher_arm / lower_arm  d<delta>. For every metric "
        "higher is better\nexcept supersession_violations, where lower is "
        "better — a negative delta is the win.)\n"
    )


def _print_selectivity(scorecard: dict[str, Any]) -> None:
    print("Per selectivity — P@1 (named vs topical), all four arms")
    label_w = 14
    header = f"{'selectivity':<{label_w}}" + "".join(f"  {arm:>14}" for arm in ARMS)
    print(header)
    print("-" * len(header))
    sels = sorted(
        {s for arm in ARMS for s in scorecard["metrics"][arm]["by_selectivity"]}
    )
    for sel in sels:
        cells = ""
        for arm in ARMS:
            block = scorecard["metrics"][arm]["by_selectivity"].get(sel, {})
            val = block.get("p_at_1", 0.0)
            cells += f"  {val:>14.6f}"
        print(f"{sel:<{label_w}}{cells}")
    print()


def _print_single(scorecard: dict[str, Any]) -> None:
    _print_arms_table(scorecard)
    _print_selectivity(scorecard)
    _print_comparisons(scorecard)


# --- driver ---------------------------------------------------------------


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
    _print_single(scorecard)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
