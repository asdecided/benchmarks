# SPDX-License-Identifier: Apache-2.0
"""The gate: compare current ``metrics`` against floors and a committed baseline.

Same semantics as ``rac eval --check``: the gate FAILS when (a)
``negative_violations`` exceeds its configured limit, (b) any gated metric
falls below its floor, or (c) any gated metric falls below
``baseline − tolerance``. On failure it prints one line per fired rule naming
the rule, the metric, and both values. Baselines are updated only by a human
running ``--update-baseline``; CI never rebaselines.

Gated metrics are whatever the committed config's ``floors`` declare — the
config is the single enumeration, so a retrieval benchmark gates
``overall.p_at_1`` / ``overall.r_at_5`` / ``overall.mrr`` while a conformance
benchmark gates ``overall.conformance`` at 1.0, without the gate code forking
per benchmark.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

RULE_NEGATIVE = "negative_violations"
RULE_FLOOR = "floor"
RULE_REGRESSION = "regression"


@dataclass(frozen=True)
class GateFailure:
    """One fired gate rule, with the metric and the values that fired it."""

    rule: str
    metric: str
    threshold: float
    current: float

    def render(self) -> str:
        if self.rule == RULE_NEGATIVE:
            return (
                f"FAIL [negative_violations] {self.metric}: "
                f"limit {self.threshold:.0f}, current {self.current:.0f}"
            )
        label = "floor" if self.rule == RULE_FLOOR else "baseline"
        return (
            f"FAIL [{self.rule}] {self.metric}: "
            f"{label} {self.threshold:.6f}, current {self.current:.6f}"
        )


def _gated_pairs(floors: dict[str, Any]) -> list[tuple[str, str, str]]:
    """The (scope, name, metric) triples the floors declare beyond negatives."""
    pairs: list[tuple[str, str, str]] = []
    for metric in sorted(floors.get("overall", {})):
        pairs.append(("overall", "", metric))
    for category in sorted(floors.get("by_category", {})):
        for metric in sorted(floors["by_category"][category]):
            pairs.append(("by_category", category, metric))
    return pairs


def _metric_value(metrics: dict[str, Any], scope: str, name: str, metric: str) -> float | None:
    block = metrics.get(scope, {})
    value = block.get(metric) if scope == "overall" else block.get(name, {}).get(metric)
    return float(value) if value is not None else None


def _floor(floors: dict[str, Any], scope: str, name: str, metric: str) -> float | None:
    if scope == "overall":
        value = floors.get("overall", {}).get(metric)
    else:
        value = floors.get(scope, {}).get(name, {}).get(metric)
    return float(value) if value is not None else None


def evaluate_gate(
    current: dict[str, Any], baseline: dict[str, Any], config: dict[str, Any]
) -> list[GateFailure]:
    """One :class:`GateFailure` per fired rule, in a deterministic order."""
    failures: list[GateFailure] = []
    tolerance = float(config["tolerance"])
    floors = config["floors"]

    # (a) Hard-negative violations — always gated, floor is the configured max.
    negatives = int(current.get("overall", {}).get("negative_violations", 0))
    negatives_max = int(floors.get("negative_violations", 0))
    if negatives > negatives_max:
        failures.append(
            GateFailure(RULE_NEGATIVE, "overall.negative_violations", negatives_max, negatives)
        )

    for scope, name, metric in _gated_pairs(floors):
        dotted = f"{scope}.{name}.{metric}" if name else f"{scope}.{metric}"
        value = _metric_value(current, scope, name, metric)
        if value is None:
            # A gated metric the current run does not report (e.g. a category
            # that vanished from the query set) is itself a regression.
            missing_floor = _floor(floors, scope, name, metric)
            failures.append(
                GateFailure(
                    RULE_FLOOR, dotted, missing_floor if missing_floor is not None else 0.0, 0.0
                )
            )
            continue
        floor = _floor(floors, scope, name, metric)
        if floor is not None and value < floor:
            failures.append(GateFailure(RULE_FLOOR, dotted, floor, value))
        base = _metric_value(baseline, scope, name, metric)
        if base is not None and value < base - tolerance:
            failures.append(GateFailure(RULE_REGRESSION, dotted, base, value))
    return failures
