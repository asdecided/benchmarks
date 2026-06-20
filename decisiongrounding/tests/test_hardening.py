"""Coverage for the run-robustness layer: word-boundary scoring, preflight
fail-fast, and durable per-cell streaming that survives a failing cell."""

import json
from pathlib import Path

import pytest

from providers.base import Action, ProposedChange
from runner.cli import _execute_runs, _preflight
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
    # Point RAC_BIN at something guaranteed absent so the check is hermetic.
    monkeypatch.setenv("RAC_BIN", "definitely-not-a-real-binary-xyz")
    with pytest.raises(SystemExit) as exc:
        _preflight(("rac",), "offline-stub", "local-hash")
    assert "rac" in str(exc.value)


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
