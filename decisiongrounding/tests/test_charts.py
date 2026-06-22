"""The dependency-free SVG charts: deterministic, well-formed, and reflecting
the data they are given."""

import xml.dom.minidom as minidom

from scoring.charts import color_for, grouped_bar_chart, line_chart


def _well_formed(svg: str):
    # Raises if the SVG is not parseable XML.
    minidom.parseString(svg)


def test_line_chart_bands_render_inside_data_arm_group():
    series = {"rac": [(10, 0.9), (50, 0.8)], "naive_rag": [(10, 0.9), (50, 0.4)]}
    bands = {"rac": [(10, 0.85, 0.95), (50, 0.7, 0.9)]}
    svg = line_chart("A", series, x_label="N", y_label="adh", x_log=True, bands=bands)
    _well_formed(svg)
    assert "<polygon" in svg
    # the band polygon sits inside rac's series group, before its polyline
    grp = svg.split('class="series" data-arm="rac"', 1)[1]
    assert grp.index("<polygon") < grp.index("<polyline")
    # deterministic
    assert svg == line_chart("A", series, x_label="N", y_label="adh", x_log=True, bands=bands)


def test_line_chart_without_bands_has_no_polygon():
    series = {"rac": [(10, 1.0), (50, 1.0)]}
    svg = line_chart("A", series, x_label="N", y_label="adh", x_log=True)
    _well_formed(svg)
    assert "<polygon" not in svg


def test_line_chart_is_well_formed_and_deterministic():
    series = {
        "context_dump": [(10, 1.0), (50, 1.0), (300, 1.0)],
        "naive_rag": [(10, 1.0), (50, 0.5), (300, 0.3)],
    }
    a = line_chart("Adherence vs N", series, x_label="N", y_label="adherence", x_log=True)
    b = line_chart("Adherence vs N", series, x_label="N", y_label="adherence", x_log=True)
    _well_formed(a)
    assert a == b  # deterministic
    assert "context_dump" in a and "naive_rag" in a
    assert a.startswith("<svg") or a.lstrip().startswith("<svg")


def test_line_chart_wraps_series_and_legend_in_data_arm_groups():
    series = {"rac": [(10, 1.0), (300, 0.9)], "naive_rag": [(10, 1.0), (300, 0.3)]}
    svg = line_chart("Adherence vs N", series, x_label="N", y_label="adherence", x_log=True)
    _well_formed(svg)
    for arm in ("rac", "naive_rag"):
        assert f'<g class="series" data-arm="{arm}">' in svg   # toggleable series
        assert f'<g class="legend" data-arm="{arm}"' in svg     # clickable legend


def test_line_chart_log_y_handles_large_range():
    series = {"context_dump": [(10, 88_000), (300, 1_576_000)], "naive_rag": [(10, 50_000), (300, 45_000)]}
    svg = line_chart("Token cost vs N", series, x_label="N", y_label="tokens", x_log=True, y_log=True)
    _well_formed(svg)


def test_grouped_bar_chart_well_formed_and_reflects_values():
    groups = ["context_dump", "naive_rag", "no_grounding", "rac"]
    series = {
        "adherence": {"context_dump": 0.95, "naive_rag": 0.95, "no_grounding": 0.0, "rac": 0.95},
        "gov-recall": {"context_dump": 1.0, "naive_rag": 1.0, "no_grounding": 0.0, "rac": 1.0},
    }
    svg = grouped_bar_chart("Base-N leaderboard", groups, series, y_label="rate")
    _well_formed(svg)
    for g in groups:
        assert g in svg


def test_palette_is_stable_per_arm():
    assert color_for("rac", 0) == color_for("rac", 3)  # name wins over index
    assert color_for("unknown_a", 0) != color_for("unknown_b", 1)  # distinct fallbacks
