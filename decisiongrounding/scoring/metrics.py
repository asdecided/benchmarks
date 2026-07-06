"""Metric aggregation over scored runs.

Headline metric: decision-adherence rate. Also: stale-decision rate,
false-permit rate, false-prohibit rate, and per-arm run-to-run variance. No
MemScore-style composite — the headline stays a single, legible rate.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import mean, pvariance, stdev


def _rate(flags: list[bool]) -> float:
    return sum(1 for f in flags if f) / len(flags) if flags else 0.0


@dataclass(frozen=True)
class ArmMetrics:
    arm: str
    n_runs: int
    adherence_rate: float
    stale_decision_rate: float
    false_permit_rate: float
    false_prohibit_rate: float
    governing_recall_rate: float | None
    # Cells that errored out for this arm (a schema-miss that exhausted every
    # retry, an HTTP failure, ...) and the total attempted (n_runs + n_errors
    # + n_context_exceeded). A rate above is averaged over `n_runs` completed
    # cells ONLY — when n_errors or n_context_exceeded > 0 that is partial
    # coverage, not the full scenario set, and must not be reported/quoted as
    # a full result.
    n_errors: int = 0
    # Cells that hit the answering model's context window (grounding + scaffold
    # + task would not fit) — tracked separately from n_errors: it is a
    # different outcome. The arm never got a chance to answer at all, rather
    # than answering-and-being-scored or hitting a transient transport/schema
    # failure. See providers.base.ContextWindowExceededError.
    n_context_exceeded: int = 0

    @property
    def n_total(self) -> int:
        return self.n_runs + self.n_errors + self.n_context_exceeded

    @property
    def coverage(self) -> str:
        return f"{self.n_runs}/{self.n_total}"

    def as_dict(self) -> dict:
        return {
            "arm": self.arm,
            "n_runs": self.n_runs,
            "n_errors": self.n_errors,
            "n_context_exceeded": self.n_context_exceeded,
            "n_total": self.n_total,
            "adherence_rate": self.adherence_rate,
            "stale_decision_rate": self.stale_decision_rate,
            "false_permit_rate": self.false_permit_rate,
            "false_prohibit_rate": self.false_prohibit_rate,
            "governing_recall_rate": self.governing_recall_rate,
        }


def recall_rate(retrieved_flags: list) -> float | None:
    """Fraction of governed scenarios whose governing decision was retrieved.

    `retrieved_flags` entries are True/False, or None where no decision governs
    (negative control) — None is excluded. Returns None when nothing is governed.
    """
    governed = [f for f in retrieved_flags if f is not None]
    return _rate(governed) if governed else None


def aggregate(
    arm: str,
    scores: list,
    retrieved_flags: list | None = None,
    n_errors: int = 0,
    n_context_exceeded: int = 0,
) -> ArmMetrics:
    """Aggregate Score objects (and optional retrieval flags) for one arm.

    `n_errors`: cells for this arm that errored rather than scored. `n_context
    _exceeded`: cells that hit the answering model's context window and so
    never got a chance to answer — kept apart from `n_errors` so a reader can
    tell a structural ceiling from a transient failure. Both are surfaced on
    the result so a partial-coverage rate is never indistinguishable from a
    full one (see `ArmMetrics.n_errors` / `.n_context_exceeded` / `.coverage`).
    """
    return ArmMetrics(
        arm=arm,
        n_runs=len(scores),
        adherence_rate=_rate([s.adherent for s in scores]),
        stale_decision_rate=_rate([s.stale_decision_followed for s in scores]),
        false_permit_rate=_rate([s.false_permit for s in scores]),
        false_prohibit_rate=_rate([s.false_prohibit for s in scores]),
        governing_recall_rate=recall_rate(retrieved_flags) if retrieved_flags is not None else None,
        n_errors=n_errors,
        n_context_exceeded=n_context_exceeded,
    )


def adherence_variance(per_seed_rates: list[float]) -> float:
    """Population variance of an arm's adherence rate across repeated seeds.

    Run-to-run variance is itself a result: a grounding layer that is correct
    but unstable is reported as such, not smoothed over.
    """
    if len(per_seed_rates) < 2:
        return 0.0
    return pvariance(per_seed_rates)


# Two-sided 95% Student-t critical values by degrees of freedom (df = n - 1).
# Hardcoded to keep the core dependency-free (no SciPy); df >= 30 -> normal z.
_T95 = {
    1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365,
    8: 2.306, 9: 2.262, 10: 2.228, 11: 2.201, 12: 2.179, 13: 2.160, 14: 2.145,
    15: 2.131, 16: 2.120, 17: 2.110, 18: 2.101, 19: 2.093, 20: 2.086, 21: 2.080,
    22: 2.074, 23: 2.069, 24: 2.064, 25: 2.060, 26: 2.056, 27: 2.052, 28: 2.048,
    29: 2.045,
}


def t_critical_95(df: int) -> float:
    """Two-sided 95% Student-t critical value for `df` degrees of freedom.

    Falls back to the normal approximation (1.96) for df >= 30, and returns 0.0
    for df < 1 (no spread information).
    """
    if df < 1:
        return 0.0
    return _T95.get(df, 1.96)


def mean_ci(values: list[float]) -> tuple[float, float, float, float, int]:
    """Return (mean, ci_lo, ci_hi, sample_std, n) using a t-based 95% interval.

    With fewer than two values the interval collapses to the mean and the std is
    0 — a single seed reports a point, not a spurious spread.
    """
    n = len(values)
    if n == 0:
        return (0.0, 0.0, 0.0, 0.0, 0)
    m = mean(values)
    if n < 2:
        return (m, m, m, 0.0, n)
    s = stdev(values)
    half = t_critical_95(n - 1) * s / (n ** 0.5)
    return (m, m - half, m + half, s, n)


def summarize(values: list[float]) -> dict:
    """{mean, std, ci: [lo, hi], n, values} for a list of per-seed measurements."""
    m, lo, hi, s, n = mean_ci(values)
    return {"mean": m, "std": s, "ci": [lo, hi], "n": n, "values": list(values)}
