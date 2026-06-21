"""The dashboard renderer: well-formed HTML, every section present, and the
fast dataset-derived cost curve. No web framework needed — this is the pure
render path that the live UI and the static generator share."""

import html.parser

from runner.dashboard import build_dashboard, curve_from_dataset


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
                   "rac vs naive RAG", "Scenarios", "Reproduce", "<svg"):
        assert marker in out, marker
    # the failing naive_rag cell shows the warning marker in the drill-down
    assert "⚠️" in out


def test_build_dashboard_without_crossover_is_still_valid():
    out = build_dashboard(_run(), None)
    _assert_html(out)
    assert "No crossover dataset supplied" in out


def test_build_dashboard_head_to_head_verdict_reads_the_numbers():
    out = build_dashboard(_run(), _dataset())
    # naive_rag decays to 0.3 at N=300 while rac holds 1.0 -> rac-holds verdict.
    assert "rac holds adherence" in out


def test_curve_from_dataset_prefers_real_usage():
    ds = _dataset()
    ds["arms"]["rac"][0]["input_tokens_mean"] = 9999  # measured beats estimate
    curve = curve_from_dataset(ds)
    assert curve["rac"][10] == 9999
    assert curve["naive_rag"][300] == 4000
    assert curve_from_dataset(None) is None
