"""Coverage for the run-robustness layer: word-boundary scoring, preflight
fail-fast, and durable per-cell streaming that survives a failing cell."""

import json
from pathlib import Path

import pytest

from providers.base import Action, ProposedChange
from runner.cli import _execute_runs, _preflight, _print_metrics, _write_report
from scenarios.loader import load_scenarios
from scoring.scorer import _required_present

_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS = _ROOT / "scenarios"


def _pc(summary: str) -> ProposedChange:
    return ProposedChange(summary=summary, actions=[], asserts_permission=True)


def test_required_present_matches_whole_words():
    # "structured json" is satisfied by a phrase containing both whole words,
    # in order, with other words between.
    assert _required_present(
        ("structured json",), _pc("emit structured, machine-readable JSON logs")
    )


def test_required_present_rejects_substring_collision():
    # "json" must NOT be satisfied by an unrelated word that merely contains it.
    assert not _required_present(("json",), _pc("we will jsonify the payload"))


def test_required_present_empty_is_trivially_true():
    assert _required_present((), _pc("anything"))


def test_preflight_claude_without_backend_fails_fast(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(SystemExit) as exc:
        _preflight(("context_dump",), "claude", "local-hash")
    assert "claude" in str(exc.value)


def test_preflight_rac_arm_without_cli_fails_fast(monkeypatch):
    # Point DECIDED_BIN at something guaranteed absent so the check is hermetic.
    monkeypatch.setenv("DECIDED_BIN", "definitely-not-a-real-binary-xyz")
    with pytest.raises(SystemExit) as exc:
        _preflight(("rac",), "offline-stub", "local-hash")
    assert "AsDecided Core" in str(exc.value)


def test_preflight_offline_default_passes(monkeypatch):
    # The offline spine (scripted model + local-hash) has no external needs.
    _preflight(("context_dump", "naive_rag", "no_grounding"), "offline-stub", "local-hash")


class _ExplodingModel:
    """An answering model whose name lookup is fine but respond() always raises,
    standing in for a transient API failure on a single cell."""

    name = "exploding"
    version = "0"
    temperature = None

    def respond(self, scaffold, grounding, task):
        raise RuntimeError("simulated transient backend failure")


def test_execute_runs_streams_and_survives_a_failing_cell(tmp_path):
    from providers import ScriptedAnsweringModel

    scenarios = load_scenarios(_SCENARIOS)
    assert scenarios
    sc = scenarios[0]
    partial = tmp_path / "run.partial.jsonl"

    # One good cell (scripted) and one bad cell (exploding) interleaved.
    good = ("context_dump", sc)
    # Reuse run_one's provider plumbing: the exploding model is wired via a second
    # pair that uses no_grounding so prepare() is trivial and respond() raises.
    results_good, errors_good = _execute_runs(
        [good], ScriptedAnsweringModel(seed=0), 0, "local-hash", partial
    )
    assert len(results_good) == 1 and not errors_good

    results_bad, errors_bad = _execute_runs(
        [("no_grounding", sc)], _ExplodingModel(), 0, "local-hash", partial
    )
    assert not results_bad
    assert len(errors_bad) == 1
    assert errors_bad[0]["arm"] == "no_grounding"

    # The durable sidecar holds BOTH the completed run and the error record —
    # the failing cell did not discard the cell already done.
    lines = [json.loads(line) for line in partial.read_text().splitlines()]
    records = {line["record"] for line in lines}
    assert records == {"run", "error"}


# --- partial-coverage visibility: a rate must never look like a full one ----


def _result(arm: str, sid: str, adherent: bool = True) -> dict:
    return {
        "arm": arm,
        "scenario_id": sid,
        "score": {
            "adherent": adherent, "stale_decision_followed": False,
            "false_permit": not adherent, "false_prohibit": False,
            "governing_decision_matched": True,
        },
        "retrieval": {"governing_decision_retrieved": None},
    }


def _error(arm: str, sid: str) -> dict:
    return {"arm": arm, "scenario_id": sid, "error": "RuntimeError('boom')"}


def test_print_metrics_flags_partial_coverage_and_hides_a_full_average(capsys):
    # 3 of 5 cells completed for "rac"; 2 errored. The printed rate must not
    # read as a clean 1.00 the way it would if errors were silently dropped.
    results = [_result("rac", f"s{i}") for i in range(3)]
    errors = [_error("rac", "s3"), _error("rac", "s4")]
    _print_metrics(results, errors)
    out = capsys.readouterr()
    assert "3/5" in out.out
    # the adherence cell for a partial arm is flagged, not a bare "1.00"
    assert "1.00*" in out.out
    assert "partial coverage" in out.err


def test_print_metrics_full_coverage_has_no_warning(capsys):
    results = [_result("rac", f"s{i}") for i in range(2)]
    _print_metrics(results, errors=[])
    out = capsys.readouterr()
    assert "2/2" in out.out
    assert "1.00" in out.out and "1.00*" not in out.out
    assert "partial coverage" not in out.err


def test_print_metrics_arm_with_zero_completed_cells_shows_na_not_zero(capsys):
    # An arm that errored on every cell has nothing to average — that must
    # print as n/a, not a misleading 0.00.
    _print_metrics(results=[], errors=[_error("naive_rag", "s0"), _error("naive_rag", "s1")])
    out = capsys.readouterr()
    assert "naive_rag" in out.out
    assert "0/2" in out.out
    assert "n/a" in out.out


def test_write_report_surfaces_an_arm_that_errored_on_every_cell(tmp_path):
    # naive_rag never appears in `results` (every cell errored) — it must
    # still show up in metrics_by_arm with its coverage, not vanish silently.
    results = [_result("rac", "s0")]
    errors = [_error("naive_rag", "s0"), _error("naive_rag", "s1")]
    path = _write_report(results, tmp_path, "test", errors)
    report = json.loads(path.read_text())
    assert report["metrics_by_arm"]["rac"]["n_errors"] == 0
    assert report["metrics_by_arm"]["rac"]["n_total"] == 1
    nr = report["metrics_by_arm"]["naive_rag"]
    assert nr["n_runs"] == 0 and nr["n_errors"] == 2 and nr["n_total"] == 2


def test_write_report_metrics_include_coverage_fields(tmp_path):
    results = [_result("rac", "s0"), _result("rac", "s1")]
    errors = [_error("rac", "s2")]
    path = _write_report(results, tmp_path, "test", errors)
    report = json.loads(path.read_text())
    d = report["metrics_by_arm"]["rac"]
    assert d["n_runs"] == 2 and d["n_errors"] == 1 and d["n_total"] == 3
