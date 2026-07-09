"""The dashboard renderer: well-formed HTML, every section present, and the
fast dataset-derived cost curve. No web framework needed — this is the pure
render path that the live UI and the static generator share."""

import html.parser

import pytest

from runner.dashboard import build_dashboard, curve_from_dataset, load_template, render_main


def _run():
    def cell(arm, sid, adherent, permit=True, prohibit=False, gov=True, tok=1000):
        return {
            "arm": arm, "scenario_id": sid, "corpus_size_N": 3,
            "answering_model": {"name": "claude", "version": "claude-opus-4-8",
                                "temperature": None, "seed": 0},
            "embedder": {"name": "voyage:voyage-4-large", "dim": 1024},
            "grounding": {"provider": arm, "token_estimate": tok, "artifacts_supplied": []},
            "usage": {"input_tokens": tok, "output_tokens": 150},
            "proposed_change": {"summary": f"{arm} on {sid}", "actions": [],
                                "cites_decisions": ["PEP-1"] if gov else [],
                                "asserts_prohibition": prohibit, "asserts_permission": permit},
            "score": {"adherent": adherent, "stale_decision_followed": False,
                      "false_permit": not adherent, "false_prohibit": False,
                      "governing_decision_matched": gov},
            "retrieval": {"governing_decision_retrieved": gov},
            "harness_version": "t",
        }
    runs = [
        cell("rac", "s1", True), cell("rac", "s2", True),
        cell("naive_rag", "s1", True), cell("naive_rag", "s2", False, permit=True, gov=False),
        cell("no_grounding", "s1", False, gov=None), cell("no_grounding", "s2", False, gov=None),
    ]
    metrics = {
        "rac": {"arm": "rac", "adherence_rate": 1.0, "stale_decision_rate": 0.0,
                "false_permit_rate": 0.0, "false_prohibit_rate": 0.0, "governing_recall_rate": 1.0, "n_runs": 2},
        "naive_rag": {"arm": "naive_rag", "adherence_rate": 0.5, "stale_decision_rate": 0.0,
                      "false_permit_rate": 0.5, "false_prohibit_rate": 0.0, "governing_recall_rate": 0.5, "n_runs": 2},
        "no_grounding": {"arm": "no_grounding", "adherence_rate": 0.0, "stale_decision_rate": 0.0,
                         "false_permit_rate": 1.0, "false_prohibit_rate": 0.0, "governing_recall_rate": None, "n_runs": 2},
    }
    return {"metrics_by_arm": metrics, "runs": runs, "errors": []}


def _dataset():
    return {
        "ns": [10, 300], "pool_size": 644,
        "arms": {
            "rac": [{"N": 10, "adherence_rate": 1.0, "governing_recall": 1.0, "token_estimate_mean": 5000},
                    {"N": 300, "adherence_rate": 1.0, "governing_recall": 1.0, "token_estimate_mean": 8000}],
            "naive_rag": [{"N": 10, "adherence_rate": 1.0, "governing_recall": 1.0, "token_estimate_mean": 4000},
                          {"N": 300, "adherence_rate": 0.3, "governing_recall": 0.3, "token_estimate_mean": 4000}],
        },
    }


def _assert_html(s):
    html.parser.HTMLParser().feed(s)  # raises on malformed
    assert s.lstrip().startswith("<!doctype html")


def test_build_dashboard_renders_all_sections():
    out = build_dashboard(_run(), _dataset())
    _assert_html(out)
    for marker in ("Decision Grounding Bench", "Leaderboard", "Adherence vs N",
                   "rac vs naive RAG", "Scenarios", "Signal / noise", "Reproduce", "<svg"):
        assert marker in out, marker
    # the failing naive_rag cell shows the warning marker in the drill-down
    assert "⚠️" in out


def test_dashboard_tabs_and_sections_stay_in_lockstep():
    import re
    from runner.dashboard import _TABS
    out = build_dashboard(_run(), _dataset(), live=True)
    n_tabs = len(_TABS) + 1  # + Run when live
    # every tab index t{i} has a matching section id s{i}
    for i in range(n_tabs):
        assert f"id=t{i}" in out and f"id=s{i}" in out, i
    assert "id=s6" in out  # the new Signal / noise tab's section


def test_signal_noise_tab_shows_snr_when_multiseed():
    ds = _dataset()
    ds["n_seeds"] = 3
    ds["paired"] = {"rac_vs_naive_rag": [
        {"N": 300, "diff_mean": 0.7, "diff_ci": [0.6, 0.8], "diff_std": 0.1, "n": 3, "values": []},
    ]}
    out = build_dashboard(_run(), ds)
    assert "Signal-to-noise" in out and "7.00" in out  # 0.7 / 0.1


def test_build_dashboard_without_crossover_is_still_valid():
    out = build_dashboard(_run(), None)
    _assert_html(out)
    assert "No crossover dataset supplied" in out


def test_build_dashboard_head_to_head_verdict_reads_the_numbers():
    out = build_dashboard(_run(), _dataset())
    # naive_rag decays to 0.3 at N=300 while rac holds 1.0 -> rac-holds verdict.
    assert "rac holds adherence" in out


def test_dashboard_renders_ci_and_paired_verdict():
    ds = _dataset()
    for arm in ds["arms"]:
        for p in ds["arms"][arm]:
            p["n_seeds"] = 3
            p["adherence_rate_ci"] = [max(0.0, p["adherence_rate"] - 0.05),
                                      min(1.0, p["adherence_rate"] + 0.05)]
    ds["n_seeds"] = 3
    ds["seeds"] = [0, 1, 2]
    ds["paired"] = {"rac_vs_naive_rag": [
        {"N": 10, "diff_mean": 0.0, "diff_ci": [-0.02, 0.02], "diff_std": 0.01, "n": 3, "values": []},
        {"N": 300, "diff_mean": 0.7, "diff_ci": [0.6, 0.8], "diff_std": 0.05, "n": 3, "values": []},
    ]}
    out = build_dashboard(_run(), ds, live=False)
    assert "±" in out                              # CI in the curve table
    assert "rac leads naive_rag by" in out         # paired-CI verdict at the top N


def test_progressive_enhancement_hooks_present():
    out = build_dashboard(_run(), _dataset(), live=True, paid_enabled=False)
    # leaderboard: id + sortable headers + per-arm rows
    assert "id=leaderboard" in out and "class=sort" in out
    assert 'data-arm="rac"' in out
    # scenarios: matrix id, per-scenario rows + drill-down, and the controls
    assert "id=scenario-matrix" in out
    assert 'data-scenario="s1"' in out and 'data-fail=' in out
    assert "scen-search" in out and "scen-fail" in out
    assert "filterScenarios" in out and "toggleFailures" in out
    # refresh affordance + handler exist on the live page
    assert "refreshMain()" in out


def test_render_main_returns_sections_shared_by_page_and_fragment():
    sections = render_main(_run(), _dataset(), live=True, paid_enabled=False)
    assert sections.lstrip().startswith("<section")
    # every section the fragment swap relies on, including the live Run tab
    for sid in ("id=s0", "id=s1", "id=s5", "id=s7"):
        assert sid in sections
    # render_main is the <main> inner — no shell/template wrapper
    assert "<!doctype" not in sections and "<nav>" not in sections


def test_default_template_is_a_file_with_both_placeholders():
    # The shell is a separately-managed .html file, not embedded in the .py.
    t = load_template()
    assert "<!--CHIPS-->" in t and "<!--BODY-->" in t
    # exactly one real placeholder each (the doc-comment must not duplicate them)
    assert t.count("<!--CHIPS-->") == 1 and t.count("<!--BODY-->") == 1


def test_custom_template_override_is_honored(tmp_path):
    custom = tmp_path / "mine.html"
    custom.write_text("<!doctype html><title>Mine</title><body>"
                      "<div class=chips><!--CHIPS--></div><!--BODY--></body>")
    out = build_dashboard(_run(), _dataset(), template=str(custom))
    assert "<title>Mine</title>" in out          # the user's shell is used
    assert "Leaderboard" in out and "<svg" in out  # data still injected
    assert "<!--BODY-->" not in out               # placeholder consumed


def test_template_missing_placeholder_is_a_clear_error(tmp_path):
    bad = tmp_path / "bad.html"
    bad.write_text("<html><body>no placeholders here</body></html>")
    with pytest.raises(ValueError, match="placeholder"):
        build_dashboard(_run(), _dataset(), template=str(bad))


def test_curve_from_dataset_prefers_real_usage():
    ds = _dataset()
    ds["arms"]["rac"][0]["input_tokens_mean"] = 9999  # measured beats estimate
    curve = curve_from_dataset(ds)
    assert curve["rac"][10] == 9999
    assert curve["naive_rag"][300] == 4000
    assert curve_from_dataset(None) is None
