"""--seeds spec parsing and the multi-seed CLI formatters."""

from runner.cli import _fmt_adherent, _fmt_pt, _parse_seeds


def test_parse_seeds_specs():
    assert _parse_seeds(None) is None
    assert _parse_seeds("") is None
    assert _parse_seeds("3") == [3]                 # a single value is one seed
    assert _parse_seeds("0,1,2") == [0, 1, 2]
    assert _parse_seeds("0-4") == [0, 1, 2, 3, 4]   # inclusive range
    assert _parse_seeds("0-2,5") == [0, 1, 2, 5]
    assert _parse_seeds("2,2,1") == [1, 2]          # dedup + sort


def test_fmt_pt_single_vs_multi():
    assert _fmt_pt({"adherence_rate": 0.5}, "adherence_rate") == "0.50"
    multi = {"adherence_rate": 0.5, "adherence_rate_ci": [0.4, 0.6], "n_seeds": 3}
    assert _fmt_pt(multi, "adherence_rate") == "0.50±0.10"
    assert _fmt_pt({"governing_recall": None}, "governing_recall") == "n/a"


def test_fmt_adherent_bool_vs_fraction():
    assert _fmt_adherent(True) == "1"
    assert _fmt_adherent(False) == "0"
    assert _fmt_adherent(0.6) == "0.6"
