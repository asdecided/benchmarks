"""Variance statistics: the t-based CI helpers behind multi-seed reporting.
Deterministic, dependency-free (no SciPy)."""

import statistics

from scoring.metrics import mean_ci, summarize, t_critical_95


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
