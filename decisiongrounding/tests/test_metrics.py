"""Variance statistics: the t-based CI helpers behind multi-seed reporting.
Deterministic, dependency-free (no SciPy)."""

import statistics

from scoring.metrics import aggregate, mean_ci, summarize, t_critical_95
from scoring.scorer import Score


def _score(adherent: bool) -> Score:
    return Score(
        adherent=adherent, stale_decision_followed=False,
        false_permit=not adherent, false_prohibit=False,
        governing_decision_matched=True,
    )


# --- partial coverage: a rate must never look like a full one ---------------


def test_aggregate_defaults_to_zero_errors_and_full_coverage():
    m = aggregate("rac", [_score(True), _score(True)])
    assert m.n_runs == 2 and m.n_errors == 0 and m.n_total == 2
    assert m.coverage == "2/2"


def test_aggregate_records_errors_against_the_full_attempted_total():
    # 3 of 5 cells completed (both adherent); 2 errored out. The rate is
    # still computed over the 3 that scored, but n_total/coverage expose the
    # partial coverage the rate doesn't capture on its own.
    m = aggregate("rac", [_score(True), _score(True), _score(True)], n_errors=2)
    assert m.n_runs == 3
    assert m.n_errors == 2
    assert m.n_total == 5
    assert m.coverage == "3/5"
    assert m.adherence_rate == 1.0  # averaged over completed cells only


def test_aggregate_as_dict_carries_coverage_fields():
    d = aggregate("rac", [_score(True)], n_errors=1).as_dict()
    assert d["n_runs"] == 1 and d["n_errors"] == 1 and d["n_total"] == 2


def test_aggregate_arm_with_zero_completed_cells():
    # Every cell for this arm errored: no scores at all, but the error count
    # must still surface rather than the arm silently vanishing.
    m = aggregate("rac", [], n_errors=4)
    assert m.n_runs == 0 and m.n_errors == 4 and m.n_total == 4
    assert m.adherence_rate == 0.0


def test_t_critical_95_table_and_normal_fallback():
    assert t_critical_95(1) == 12.706
    assert t_critical_95(4) == 2.776          # 5 seeds -> df 4
    assert t_critical_95(29) == 2.045
    assert t_critical_95(30) == 1.96          # df >= 30 -> normal approximation
    assert t_critical_95(500) == 1.96
    assert t_critical_95(0) == 0.0            # no spread information


def test_mean_ci_single_value_is_a_point():
    assert mean_ci([0.7]) == (0.7, 0.7, 0.7, 0.0, 1)


def test_mean_ci_empty():
    assert mean_ci([]) == (0.0, 0.0, 0.0, 0.0, 0)


def test_mean_ci_matches_t_formula():
    vals = [0.4, 0.6, 0.5, 0.5, 0.5]
    m, lo, hi, std, n = mean_ci(vals)
    assert n == 5 and abs(m - 0.5) < 1e-12
    s = statistics.stdev(vals)
    half = 2.776 * s / (5 ** 0.5)
    assert abs((hi - lo) / 2 - half) < 1e-12
    assert lo < m < hi and abs(std - s) < 1e-12


def test_summarize_shape():
    s = summarize([1.0, 2.0, 3.0])
    assert s["mean"] == 2.0 and s["n"] == 3 and s["values"] == [1.0, 2.0, 3.0]
    assert len(s["ci"]) == 2 and s["std"] > 0
