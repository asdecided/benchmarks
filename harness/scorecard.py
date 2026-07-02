# SPDX-License-Identifier: Apache-2.0
"""The scorecard: gated ``metrics``, diagnostic ``metadata`` and ``per_query``.

Mirrors the grounding-eval-scorecard design shape (rac-core
``rac/designs/grounding-eval-scorecard.md``): only ``metrics`` is compared by
the gate; ``metadata`` (the ``rac --version`` string, corpus hash, query-set
hash, case count, timestamp) and ``per_query`` are diagnostic and excluded, so
a clock or hash never fails a build. The scorecard JSON is an additive, stable
contract (ADR-007): fields are never removed or renamed.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from harness.cases import K_VALUES, KIND_RETRIEVAL


@dataclass
class Scorecard:
    """A full benchmark run: gated ``metrics`` plus diagnostic context."""

    metrics: dict[str, Any]
    metadata: dict[str, Any]
    per_query: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "metrics": self.metrics,
            "metadata": self.metadata,
            "per_query": self.per_query,
        }


def corpus_hash(root: str) -> str:
    """A stable ``sha256:…`` over the fixture corpus files.

    Covers exactly the Markdown files the benchmark scores, each prefixed by
    its corpus-relative path, in sorted order.
    """
    root_path = Path(root)
    digest = hashlib.sha256()
    for file_path in sorted(root_path.rglob("*.md")):
        rel = file_path.relative_to(root_path).as_posix()
        digest.update(rel.encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def query_set_hash(path: str) -> str:
    """A stable ``sha256:…`` over the query set file bytes."""
    digest = hashlib.sha256(Path(path).read_bytes())
    return "sha256:" + digest.hexdigest()


def build_metadata(
    *,
    rac_version: str,
    root: str,
    queries_path: str,
    n_queries: int,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Diagnostic run context — excluded from the gate comparison."""
    return {
        "rac_version": rac_version,
        "corpus_hash": corpus_hash(root),
        "query_set_hash": query_set_hash(queries_path),
        "n_queries": n_queries,
        "generated_at": generated_at if generated_at is not None else _now_iso(),
    }


def _now_iso() -> str:
    """Wall-clock stamp for diagnostic metadata only (excluded from the gate)."""
    return datetime.now(UTC).isoformat()


# --- Rendering -----------------------------------------------------------------


def render_scorecard_json(scorecard: Scorecard) -> str:
    """The full scorecard as pretty JSON, key order preserved."""
    return json.dumps(scorecard.to_dict(), indent=2, ensure_ascii=False)


def render_metrics_json(metrics: dict[str, Any]) -> str:
    """The gated ``metrics`` block alone — what ``--update-baseline`` writes."""
    return json.dumps(metrics, indent=2, ensure_ascii=False)


def render_scorecard_human(scorecard: Scorecard, kind: str) -> str:
    """A terminal-legible summary: overall, by-category, then Violations."""
    metrics = scorecard.metrics
    overall = metrics["overall"]
    lines: list[str] = ["Overall"]

    if kind == KIND_RETRIEVAL:
        header = "  " + "".join(f"{f'P@{k}':>8}{f'R@{k}':>8}" for k in K_VALUES) + f"{'MRR':>8}"
        lines.append(header)
        row = "  " + "".join(
            f"{overall[f'p_at_{k}']:>8.3f}{overall[f'r_at_{k}']:>8.3f}" for k in K_VALUES
        )
        lines.append(row + f"{overall['mrr']:>8.3f}")
    else:
        lines.append(
            f"  conformance: {overall['conformance']:.3f} "
            f"({overall['cases_passed']}/{overall['cases_total']} cases)"
        )
    lines.append(f"  negative_violations: {overall['negative_violations']}")
    lines.append("")

    lines.append("By category")
    lines.extend(_render_group(metrics["by_category"]))
    lines.append("")

    lines.append("Violations")
    offenders = [entry for entry in scorecard.per_query if entry.get("violations")]
    failures = [
        entry
        for entry in scorecard.per_query
        if "passed" in entry and not entry["passed"] and not entry.get("violations")
    ]
    if not offenders and not failures:
        lines.append("  none")
    for offender in offenders:
        lines.append(f"  {offender['id']}: returned {offender['violations']}")
    for failure in failures:
        failed = [c["name"] for c in failure.get("checks", []) if not c["passed"]]
        lines.append(f"  {failure['id']}: failed checks {failed}")
    return "\n".join(lines)


def _render_group(group: dict[str, Any]) -> list[str]:
    if not group:
        return ["  (none)"]
    width = max(len(name) for name in group)
    metric_names = sorted({metric for cell in group.values() for metric in cell})
    header = "  " + " " * width + "".join(f"{name:>14}" for name in metric_names)
    lines = [header]
    for name in group:
        cell = group[name]
        row = f"  {name:{width}}"
        for metric in metric_names:
            value = cell.get(metric)
            row += f"{value:>14.3f}" if value is not None else f"{'-':>14}"
        lines.append(row)
    return lines
