"""The results page states its provenance, configs, and variance."""
from pathlib import Path

from scoring.aggregate import aggregate
from scoring.report import render_html, render_markdown, write_report
from scoring.scorer import score_records
from tests.test_scoring import STABLE_STDOUT, UNSTABLE_STDOUT, make_record


def scored_pair():
    return score_records([
        make_record(),
        make_record(stdout=UNSTABLE_STDOUT, exit_code=1, verified=False),
    ])


def test_scripted_results_carry_the_illustration_notice():
    scores = scored_pair()
    markdown = render_markdown(scores, aggregate(scores), label="t")
    assert "Harness illustration, not a benchmark result" in markdown


def test_page_reports_variance_for_repeats():
    scores = scored_pair()
    markdown = render_markdown(scores, aggregate(scores), label="t")
    assert "## Run-to-run variance" in markdown
    assert "| 0.5 | 0.25 |" in markdown


def test_page_lists_every_run_with_its_config():
    scores = scored_pair()
    markdown = render_markdown(scores, aggregate(scores), label="t")
    assert "Every run, with its exact configuration" in markdown
    assert markdown.count("| api-ledger | LEDGER-0000000000R1 | easy |") == 2
    assert "2026.7.1" in markdown  # the pinned agent version is on the page


def test_write_report_emits_markdown_and_html(tmp_path: Path):
    scores = scored_pair()
    md_path, html_path = write_report(scores, aggregate(scores), tmp_path, label="t")
    assert md_path.is_file() and html_path.is_file()
    html = html_path.read_text()
    assert html.startswith("<!doctype html>") and "<table>" in html


def test_html_escapes_content():
    scores = scored_pair()
    scores[0]["error"] = "<script>alert(1)</script>"
    html = render_html(render_markdown(scores, aggregate(scores), label="t"), label="t")
    assert "<script>alert(1)</script>" not in html
