"""Dependency-free SVG charts for the benchmark report.

The repo deliberately avoids a plotting dependency: charts are hand-rolled SVG so
the committed artifacts are deterministic and reproduce in CI with no matplotlib.
This module provides the two shapes the report needs — a multi-series line chart
(adherence / recall / cost vs N) and a grouped bar chart (the base-N
leaderboard) — sharing one palette and one set of axis helpers.
"""

from __future__ import annotations

import math

# Stable per-arm palette (matches the existing crossover chart).
PALETTE = {
    "context_dump": "#1f77b4",
    "naive_rag": "#d62728",
    "rac": "#2ca02c",
    "no_grounding": "#7f7f7f",
    "memory_provider": "#9467bd",
}
_FALLBACK = ["#1f77b4", "#d62728", "#2ca02c", "#9467bd", "#ff7f0e", "#7f7f7f"]


def color_for(label: str, i: int) -> str:
    return PALETTE.get(label, _FALLBACK[i % len(_FALLBACK)])


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def line_chart(
    title: str,
    series: dict[str, list[tuple[float, float]]],
    *,
    x_label: str,
    y_label: str,
    x_log: bool = False,
    y_log: bool = False,
    y_max: float | None = None,
    y_min: float | None = None,
    fmt: str = "{:.2f}",
    width: int = 720,
    height: int = 460,
) -> str:
    """Multi-series line chart. `series` maps label -> [(x, y), ...]. Set x_log
    for the N axis; y_log for cost (orders of magnitude). Returns SVG text."""
    pad_l, pad_r, pad_t, pad_b = 70, 150, 50, 55
    all_x = [x for pts in series.values() for x, _ in pts]
    all_y = [y for pts in series.values() for _, y in pts]
    if not all_x:
        all_x, all_y = [0, 1], [0, 1]

    def tx(v):
        return math.log10(v) if x_log else v

    def ty(v):
        return math.log10(max(v, 1e-9)) if y_log else v

    xmin, xmax = min(map(tx, all_x)), max(map(tx, all_x))
    lo = y_min if y_min is not None else (min(all_y) if y_log else 0.0)
    hi = y_max if y_max is not None else max(all_y) * (1.0 if y_log else 1.05)
    ymin, ymax = ty(lo if lo > 0 or not y_log else min(v for v in all_y if v > 0) / 2), ty(hi)

    def px(x):
        return pad_l + (tx(x) - xmin) / ((xmax - xmin) or 1) * (width - pad_l - pad_r)

    def py(y):
        return height - pad_b - (ty(y) - ymin) / ((ymax - ymin) or 1) * (height - pad_t - pad_b)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="sans-serif">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<text x="{width/2}" y="26" text-anchor="middle" font-size="16" font-weight="bold">{_esc(title)}</text>',
    ]
    # y gridlines + labels
    if y_log:
        decades = range(int(math.floor(ymin)), int(math.ceil(ymax)) + 1)
        yticks = [(10.0 ** d) for d in decades]
    else:
        yticks = [ymin + (ymax - ymin) * f for f in (0, 0.25, 0.5, 0.75, 1.0)]
    for yt in yticks:
        if yt < (lo if not y_log else 0) and not y_log:
            continue
        yv = py(yt)
        parts.append(f'<line x1="{pad_l}" y1="{yv}" x2="{width-pad_r}" y2="{yv}" stroke="#eee"/>')
        lbl = (f"{yt:,.0f}" if y_log or yt >= 100 else fmt.format(yt))
        parts.append(f'<text x="{pad_l-8}" y="{yv+4}" text-anchor="end" font-size="11" fill="#444">{lbl}</text>')
    # axes
    parts.append(f'<line x1="{pad_l}" y1="{height-pad_b}" x2="{width-pad_r}" y2="{height-pad_b}" stroke="#333"/>')
    parts.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{height-pad_b}" stroke="#333"/>')
    # x ticks at the data's x values
    for xv in sorted(set(all_x)):
        parts.append(
            f'<text x="{px(xv)}" y="{height-pad_b+18}" text-anchor="middle" font-size="11" fill="#444">{_esc(xv)}</text>'
        )
    parts.append(f'<text x="{(pad_l+width-pad_r)/2}" y="{height-12}" text-anchor="middle" font-size="12">{_esc(x_label)}</text>')
    parts.append(
        f'<text x="16" y="{(pad_t+height-pad_b)/2}" text-anchor="middle" font-size="12" '
        f'transform="rotate(-90 16 {(pad_t+height-pad_b)/2})">{_esc(y_label)}</text>'
    )
    # series
    legend_y = pad_t + 6
    for i, (label, pts) in enumerate(series.items()):
        c = color_for(label, i)
        pts = sorted(pts)
        poly = " ".join(f"{px(x):.1f},{py(y):.1f}" for x, y in pts)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="{c}" stroke-width="2.5"/>')
        for x, y in pts:
            parts.append(f'<circle cx="{px(x):.1f}" cy="{py(y):.1f}" r="3.5" fill="{c}"/>')
        parts.append(f'<rect x="{width-pad_r+8}" y="{legend_y-9}" width="11" height="11" fill="{c}"/>')
        parts.append(f'<text x="{width-pad_r+24}" y="{legend_y}" font-size="12" fill="#222">{_esc(label)}</text>')
        legend_y += 18
    parts.append("</svg>")
    return "\n".join(parts)


def grouped_bar_chart(
    title: str,
    groups: list[str],
    series: dict[str, dict[str, float]],
    *,
    y_label: str,
    y_max: float = 1.0,
    fmt: str = "{:.2f}",
    width: int = 760,
    height: int = 460,
) -> str:
    """Grouped bars: one cluster per `group` (e.g. arm), one bar per `series`
    key (e.g. metric). `series[name][group]` is the height in [0, y_max]."""
    pad_l, pad_r, pad_t, pad_b = 60, 150, 50, 70
    plot_w = width - pad_l - pad_r
    plot_h = height - pad_t - pad_b
    n_groups = max(len(groups), 1)
    n_series = max(len(series), 1)
    group_w = plot_w / n_groups
    bar_w = group_w * 0.8 / n_series

    def py(v):
        return pad_t + plot_h - (v / (y_max or 1)) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" font-family="sans-serif">',
        f'<rect width="{width}" height="{height}" fill="white"/>',
        f'<text x="{width/2}" y="26" text-anchor="middle" font-size="16" font-weight="bold">{_esc(title)}</text>',
    ]
    for f in (0, 0.25, 0.5, 0.75, 1.0):
        yv = py(y_max * f)
        parts.append(f'<line x1="{pad_l}" y1="{yv}" x2="{width-pad_r}" y2="{yv}" stroke="#eee"/>')
        parts.append(f'<text x="{pad_l-8}" y="{yv+4}" text-anchor="end" font-size="11" fill="#444">{fmt.format(y_max*f)}</text>')
    parts.append(f'<line x1="{pad_l}" y1="{pad_t+plot_h}" x2="{width-pad_r}" y2="{pad_t+plot_h}" stroke="#333"/>')
    parts.append(f'<line x1="{pad_l}" y1="{pad_t}" x2="{pad_l}" y2="{pad_t+plot_h}" stroke="#333"/>')
    parts.append(
        f'<text x="16" y="{pad_t+plot_h/2}" text-anchor="middle" font-size="12" '
        f'transform="rotate(-90 16 {pad_t+plot_h/2})">{_esc(y_label)}</text>'
    )
    series_names = list(series)
    for gi, g in enumerate(groups):
        gx = pad_l + gi * group_w
        for si, name in enumerate(series_names):
            v = series[name].get(g, 0) or 0
            bx = gx + group_w * 0.1 + si * bar_w
            by = py(v)
            c = _FALLBACK[si % len(_FALLBACK)]
            parts.append(f'<rect x="{bx:.1f}" y="{by:.1f}" width="{bar_w:.1f}" height="{pad_t+plot_h-by:.1f}" fill="{c}"/>')
            parts.append(f'<text x="{bx+bar_w/2:.1f}" y="{by-3:.1f}" text-anchor="middle" font-size="9" fill="#333">{fmt.format(v)}</text>')
        parts.append(f'<text x="{gx+group_w/2:.1f}" y="{pad_t+plot_h+18}" text-anchor="middle" font-size="11">{_esc(g)}</text>')
    legend_y = pad_t + 6
    for si, name in enumerate(series_names):
        c = _FALLBACK[si % len(_FALLBACK)]
        parts.append(f'<rect x="{width-pad_r+8}" y="{legend_y-9}" width="11" height="11" fill="{c}"/>')
        parts.append(f'<text x="{width-pad_r+24}" y="{legend_y}" font-size="12" fill="#222">{_esc(name)}</text>')
        legend_y += 18
    parts.append("</svg>")
    return "\n".join(parts)
