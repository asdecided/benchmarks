"""Render the results page from scored, aggregated run records.

Markdown first (per the family's ADR-001 lineage), with a plain static HTML
rendering of the same content. Every published number is traceable: each run
row carries its exact harness configuration, and repeated configurations get
their run-to-run variance stated on the page rather than in a footnote.
Scripted-mode runs are labelled harness illustrations, never benchmark
results.
"""
from __future__ import annotations

import html
from pathlib import Path

from runner import HARNESS_VERSION


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.0f}%"


def _bucket_row(name: str, bucket: dict) -> str:
    return (f"| {name} | {bucket['runs']} | {_pct(bucket['verified_rate'])} "
            f"| {_pct(bucket['negative_path_rate'])} | {_pct(bucket['honesty_rate'])} "
            f"| {bucket['false_verify_count']} | {bucket['prompt_tokens']} "
            f"| {bucket['completion_tokens']} | {bucket['wall_clock_s']}s |")


_BUCKET_HEADER = (
    "| | runs | verified | negative paths | honesty | false verifies "
    "| tokens in | tokens out | wall clock |\n"
    "|---|---|---|---|---|---|---|---|---|"
)


def render_markdown(scores: list[dict], aggregates: dict, *, label: str) -> str:
    lines: list[str] = []
    lines.append("# autonomousqa results")
    lines.append("")
    lines.append(f"Harness v{HARNESS_VERSION} — result set `{label}`.")
    lines.append("")
    estimated = aggregates["overall"]["usage_estimated"]
    if estimated:
        lines.append("> **Harness illustration, not a benchmark result.** This result set")
        lines.append("> contains scripted-model runs: the drive was replayed from a canned")
        lines.append("> flow and token counts are deterministic estimates. It demonstrates")
        lines.append("> the pipeline end to end; published benchmark numbers come from")
        lines.append("> BYOK runs against real providers.")
        lines.append("")
    lines.append("Scoring is deterministic: a capability is verified iff the agent's")
    lines.append("fidelity gate passed, re-derived from the recorded raw evidence — no")
    lines.append("embeddings, no LLM judge. \"Honesty\" is scored on the deliberately")
    lines.append("ambiguous capabilities each corpus seeds: an honest agent leaves them")
    lines.append("unverified.")
    lines.append("")
    for title, key in (("Overall", None), ("By app", "by_app"),
                       ("By modality", "by_modality"), ("By model", "by_model"),
                       ("By tier", "by_tier")):
        lines.append(f"## {title}")
        lines.append("")
        lines.append(_BUCKET_HEADER)
        if key is None:
            lines.append(_bucket_row("all runs", aggregates["overall"]))
        else:
            for name, bucket in aggregates[key].items():
                lines.append(_bucket_row(name, bucket))
        lines.append("")
    lines.append("## Run-to-run variance")
    lines.append("")
    if aggregates["run_to_run"]:
        lines.append("| app | capability | agent | model | mode | repeats | verified mean | variance |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for row in aggregates["run_to_run"]:
            lines.append(f"| {row['app']} | {row['capability_id']} | {row['agent']} "
                         f"| {row['model']} | {row['mode']} | {row['repeats']} "
                         f"| {row['verified_mean']} | {row['verified_variance']} |")
    else:
        lines.append("No configuration was repeated in this result set; repeat a run")
        lines.append("(`--repeat N`) to publish variance alongside the rates.")
    lines.append("")
    lines.append("## Every run, with its exact configuration")
    lines.append("")
    lines.append("| app | capability | tier | agent | version | model | mode | n "
                 "| verified | fidelity | tokens in/out | wall clock | error |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for s in scores:
        fidelity = "—" if s["fidelity_rate"] is None else f"{s['fidelity_rate'] * 100:.0f}%"
        lines.append(
            f"| {s['app']} | {s['capability_id']} | {s['tier']} | {s['agent']} "
            f"| {s['agent_version']} | {s['model'] or '—'} | {s['mode']} | — "
            f"| {'yes' if s['verified'] else 'no'} | {fidelity} "
            f"| {s['prompt_tokens']}/{s['completion_tokens']} "
            f"| {s['wall_clock_s']}s | {s['error'] or '—'} |")
    lines.append("")
    return "\n".join(lines)


def render_html(markdown: str, *, label: str) -> str:
    """A minimal static rendering: the Markdown, made table-readable."""
    rows = []
    in_table = False
    for line in markdown.split("\n"):
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(set(c) <= {"-"} for c in cells):
                continue
            tag = "th" if not in_table else "td"
            rows.append("<tr>" + "".join(f"<{tag}>{html.escape(c)}</{tag}>" for c in cells) + "</tr>")
            in_table = True
            continue
        if in_table:
            rows.append("</table>")
            in_table = False
        if line.startswith("# "):
            rows.append(f"<h1>{html.escape(line[2:])}</h1>")
        elif line.startswith("## "):
            rows.append(f"<h2>{html.escape(line[3:])}</h2>")
        elif line.startswith("> "):
            rows.append(f"<p class='notice'>{html.escape(line[2:])}</p>")
        elif line.strip():
            rows.append(f"<p>{html.escape(line)}</p>")
    if in_table:
        rows.append("</table>")
    body = "\n".join(rows).replace("<tr><th", "<table>\n<tr><th", 1)
    # Re-open a table after each close if another header row follows.
    body = body.replace("</table>\n<tr><th", "</table>\n<table>\n<tr><th")
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>autonomousqa results — {html.escape(label)}</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 72rem; margin: 2rem auto; padding: 0 1rem; color: #1c2733; }}
  table {{ border-collapse: collapse; margin: 1rem 0; font-size: 0.9rem; }}
  th, td {{ border: 1px solid #d5dde5; padding: 0.35rem 0.6rem; text-align: left; }}
  th {{ background: #eef2f6; }}
  .notice {{ background: #fff6e0; border-left: 4px solid #d99b00; padding: 0.5rem 0.75rem; }}
</style>
</head>
<body>
{body}
</body>
</html>
"""


def write_report(scores: list[dict], aggregates: dict, out_dir: Path, *, label: str) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    markdown = render_markdown(scores, aggregates, label=label)
    md_path = out_dir / f"{label}.md"
    html_path = out_dir / f"{label}.html"
    md_path.write_text(markdown)
    html_path.write_text(render_html(markdown, label=label))
    return md_path, html_path
