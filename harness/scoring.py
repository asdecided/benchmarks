# SPDX-License-Identifier: Apache-2.0
"""Deterministic scoring — a pure function of the returned contract payloads.

Retrieval benchmarks score Precision@k / Recall@k (``k ∈ {1, 3, 5}``,
macro-averaged) plus MRR — the rank-aware statistic that catches within-top-5
ordering regressions the P@1 / R@5 floors are blind to — and count
hard-negative violations over the FULL returned list, not a top-k window: a
``must_not_return`` id anywhere in the returned list reaches an agent, so it
is a violation wherever it ranks.

Conformance benchmarks score a pass rate over deterministic contract checks,
gated at 1.0 — a contract is either honoured or it is not.

Floats are rounded to a fixed precision so the serialized ``metrics`` block is
byte-stable across runs on an unchanged corpus (ADR-066).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from harness.cases import K_VALUES, RetrievalCase

# Metric floats are rounded to this many decimals so the serialized ``metrics``
# object is byte-identical across runs (the gate compares with tolerance, far
# coarser than this precision, so rounding never hides a real regression).
_PRECISION: int = 6


def _round(value: float) -> float:
    return round(value, _PRECISION)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# --- Retrieval kind -----------------------------------------------------------


@dataclass
class RetrievalResult:
    """The scored outcome of one :class:`RetrievalCase` — a ``per_query`` row."""

    case: RetrievalCase
    returned: list[str]
    precision: dict[int, float]
    recall: dict[int, float]
    reciprocal_rank: float
    violations: list[str]

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.case.id,
            "category": self.case.category,
            "query": self.case.query,
            "returned": self.returned,
            "relevant": list(self.case.relevant),
        }
        if self.case.must_not_return:
            payload["must_not_return"] = list(self.case.must_not_return)
        for k in K_VALUES:
            payload[f"p_at_{k}"] = _round(self.precision[k])
        for k in K_VALUES:
            payload[f"r_at_{k}"] = _round(self.recall[k])
        payload["reciprocal_rank"] = _round(self.reciprocal_rank)
        payload["violations"] = self.violations
        return payload


def score_retrieval_case(returned: list[str], case: RetrievalCase) -> RetrievalResult:
    """P@k, R@k, reciprocal rank, and full-list negative violations for one case.

    ``P@k = |Rel ∩ top_k| / k`` (empty slots count against precision);
    ``R@k = |Rel ∩ top_k| / |Rel|`` (``|Rel| ≥ 1`` by construction). The
    reciprocal rank is ``1 / rank`` of the first relevant id in the full
    returned list, 0.0 when none is returned. A violation is a
    ``must_not_return`` id ANYWHERE in the returned list.
    """
    relevant = set(case.relevant)
    precision: dict[int, float] = {}
    recall: dict[int, float] = {}
    for k in K_VALUES:
        top_k = returned[:k]
        hits = sum(1 for rid in top_k if rid in relevant)
        precision[k] = hits / k
        recall[k] = hits / len(relevant)
    reciprocal_rank = 0.0
    for rank, rid in enumerate(returned, start=1):
        if rid in relevant:
            reciprocal_rank = 1.0 / rank
            break
    negatives = set(case.must_not_return)
    violations = sorted(rid for rid in returned if rid in negatives)
    return RetrievalResult(
        case=case,
        returned=returned,
        precision=precision,
        recall=recall,
        reciprocal_rank=reciprocal_rank,
        violations=violations,
    )


def aggregate_retrieval(results: list[RetrievalResult]) -> dict[str, Any]:
    """Macro-averaged ``metrics`` for a retrieval benchmark.

    ``overall`` carries the gated statistics (P@k, R@k, MRR,
    ``negative_violations``); ``by_category`` mirrors the gate's breakdown
    surface (p_at_1 / r_at_5 / mrr per category, equal weight per case).
    """
    overall: dict[str, Any] = {}
    for k in K_VALUES:
        overall[f"p_at_{k}"] = _round(_mean([r.precision[k] for r in results]))
    for k in K_VALUES:
        overall[f"r_at_{k}"] = _round(_mean([r.recall[k] for r in results]))
    overall["mrr"] = _round(_mean([r.reciprocal_rank for r in results]))
    overall["negative_violations"] = sum(len(r.violations) for r in results)

    groups: dict[str, list[RetrievalResult]] = {}
    for result in results:
        groups.setdefault(result.case.category, []).append(result)
    by_category: dict[str, Any] = {}
    for name in sorted(groups):
        members = groups[name]
        by_category[name] = {
            "p_at_1": _round(_mean([r.precision[1] for r in members])),
            "r_at_5": _round(_mean([r.recall[5] for r in members])),
            "mrr": _round(_mean([r.reciprocal_rank for r in members])),
        }
    return {"overall": overall, "by_category": by_category}


# --- Conformance kind ----------------------------------------------------------


@dataclass
class Check:
    """One named deterministic assertion inside a conformance case."""

    name: str
    passed: bool
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": self.name, "passed": self.passed}
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass
class ConformanceResult:
    """The scored outcome of one contract case — a ``per_query`` row."""

    case_id: str
    category: str
    checks: list[Check]
    violations: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks) and not self.violations

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.case_id,
            "category": self.category,
            "passed": self.passed,
            "checks": [check.to_dict() for check in self.checks],
        }
        payload.update(self.context)
        payload["violations"] = self.violations
        return payload


def aggregate_conformance(results: list[ConformanceResult]) -> dict[str, Any]:
    """``metrics`` for a conformance benchmark: pass rate, gated at 1.0."""
    passed = sum(1 for r in results if r.passed)
    overall: dict[str, Any] = {
        "conformance": _round(passed / len(results)) if results else 0.0,
        "cases_passed": passed,
        "cases_total": len(results),
        "negative_violations": sum(len(r.violations) for r in results),
    }
    groups: dict[str, list[ConformanceResult]] = {}
    for result in results:
        groups.setdefault(result.category, []).append(result)
    by_category: dict[str, Any] = {}
    for name in sorted(groups):
        members = groups[name]
        by_category[name] = {
            "conformance": _round(sum(1 for r in members if r.passed) / len(members)),
        }
    return {"overall": overall, "by_category": by_category}
