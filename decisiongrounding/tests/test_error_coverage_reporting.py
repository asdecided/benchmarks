"""Reporting layer surfaces error-cell coverage: the crossover curve tables
flag partial-coverage cells, and the demo summary classifies error kinds."""

from scripts import report as report_mod
from runner import dashboard as dash_mod


def _dataset_with_error_cell():
    """One arm, two N points; the N=50 point had one error cell."""
    return {
        "ns": [10, 50],
        "arms": {
            "context_dump": [
                {"N": 10, "adherence_rate": 1.0, "attempted": 3,
                 "error_count": 0, "context_window_exceeded_count": 0},
                {"N": 50, "adherence_rate": 1.0, "attempted": 2,
                 "error_count": 1, "context_window_exceeded_count": 0},
            ],
        },
    }


def test_report_curve_flags_partial_coverage_cell():
    out = report_mod._curve_table(_dataset_with_error_cell(),
                                  "adherence_rate", "Adherence")
    # the N=50 cell (error_count=1) is starred; the N=10 cell is not
    assert "1.00*" in out
    assert "partial coverage" in out


def test_report_curve_no_flag_when_complete():
    ds = _dataset_with_error_cell()
    ds["arms"]["context_dump"][1]["error_count"] = 0
    out = report_mod._curve_table(ds, "adherence_rate", "Adherence")
    assert "*" not in out
    assert "partial coverage" not in out


def test_report_non_adherence_curve_never_flagged():
    # token/recall curves are not coverage-flagged — only adherence excludes cells
    ds = _dataset_with_error_cell()
    ds["arms"]["context_dump"][1]["token_estimate_mean"] = 42.0
    out = report_mod._curve_table(ds, "token_estimate_mean", "Tokens")
    assert "*" not in out


def test_dashboard_curve_flags_partial_coverage_cell():
    out = dash_mod._curve_table(_dataset_with_error_cell(), "adherence_rate")
    assert "*" in out
    assert "partial coverage" in out


def test_legacy_dataset_without_error_fields_reads_clean():
    legacy = {
        "ns": [10],
        "arms": {"context_dump": [{"N": 10, "adherence_rate": 1.0}]},
    }
    out = report_mod._curve_table(legacy, "adherence_rate", "Adherence")
    assert "1.00" in out and "*" not in out
