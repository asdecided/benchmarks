"""Holm correction + family labels render in the report and the paper table."""

from pathlib import Path

from scoring.stats import annotate_holm_family, stats_by_n
from scripts.paper_figs import write_stats_table
from scripts.report import _mcnemar_line, _stats_pair_rows, _stats_section


def _annotated_stats():
    cells = []
    for n in (50, 150, 300):
        for i in range(6):
            cells.append({"seed": 0, "N": n, "arm": "rac", "scenario_id": f"s{i}", "adherent": True})
            cells.append({"seed": 0, "N": n, "arm": "naive_rag", "scenario_id": f"s{i}", "adherent": i < 2})
    stats = stats_by_n(cells)
    annotate_holm_family(stats)
    return stats


def test_pair_rows_show_holm_and_family():
    stats = _annotated_stats()
    sec = "\n".join(_stats_pair_rows(stats[50]["pairs"]))
    assert "Holm p / family" in sec
    assert "(Holm)" in sec                        # secondary cell corrected
    conf = "\n".join(_stats_pair_rows(stats[300]["pairs"]))
    assert "confirmatory (uncorr.)" in conf       # N=300 uncorrected, tagged


def test_stats_section_has_multiple_comparisons_note():
    ds = {"stats": _annotated_stats()}
    out = "\n".join(_stats_section({}, ds))
    assert "Multiple comparisons" in out and "Holm-corrected" in out
    assert "N=300" in out


def test_mcnemar_line_is_uncorrected_with_secondary_holm_summary():
    ds = {"stats": _annotated_stats()}
    line = _mcnemar_line(ds, 300)
    assert "uncorrected" in line
    assert "Holm-corrected across N" in line       # the secondary companion line


def test_paper_table_has_holm_column(tmp_path):
    out = write_stats_table({"stats": _annotated_stats()}, tmp_path)
    tex = Path(out).read_text()
    assert "Holm $p$ / family" in tex
    assert "conf.\\ (uncorr.)" in tex              # the N=300 confirmatory cell
