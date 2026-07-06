"""Context-window-exceeded as a first-class outcome.

A grounding that cannot fit the answering model's context window (typically
`context_dump` at a large N) must be recorded as its own outcome — distinct
from a generic transport/schema error — and excluded from `adherence_rate`'s
numerator AND denominator, so the crossover chart never reports a structural
ceiling as "the arm answered and got it wrong". See providers/base.py
(`ContextWindowExceededError`, `check_context_window`) and its threading
through runner/cli.py and scoring/crossover.py.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from providers import ContextWindowExceededError, ScriptedAnsweringModel
from providers.answering import _reraise_if_context_length
from providers.base import (
    RESPONSE_RESERVE_TOKENS,
    CorpusArtifact,
    GroundingContext,
    Task,
    check_context_window,
    context_window_needed,
    estimate_tokens,
)
from providers.context_dump import ContextDumpProvider
from runner.cli import _execute_runs, _print_metrics, _write_report
from scenarios.loader import load_scenarios
from scoring.crossover import build_dataset
from scoring.metrics import aggregate

_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS = _ROOT / "scenarios"

TASK = Task(prompt="Do the thing.", proposed_action="do the thing")


class _TinyWindowModel(ScriptedAnsweringModel):
    """The offline scripted model with an artificially small context window,
    so the preflight check in `Provider.respond` fires deterministically
    without needing a real backend."""

    name = "tiny-window-stub"

    def __init__(self, context_window_tokens: int, seed: int = 0) -> None:
        super().__init__(seed=seed)
        self.context_window_tokens = context_window_tokens
        self.respond_calls = 0

    def respond(self, scaffold, grounding, task):
        self.respond_calls += 1
        return super().respond(scaffold, grounding, task)


def _grounding(token_estimate: int) -> GroundingContext:
    return GroundingContext(text="x" * (token_estimate * 4), artifacts_supplied=(), token_estimate=token_estimate)


# --- check_context_window / context_window_needed ---------------------------


def test_context_window_needed_sums_scaffold_grounding_and_task():
    g = _grounding(100)
    needed = context_window_needed(g, TASK)
    expected = (
        estimate_tokens(
            "You are a senior engineer about to act on a task. Prior team decisions "
            "may bind your action. Using ONLY the grounding provided, decide whether "
            "the proposed action is permitted or prohibited, follow any superseding "
            "decision over the decision it supersedes, do not invent constraints that "
            "the grounding does not state, and cite the decision id(s) you relied on."
        )
        + 100
        + estimate_tokens(TASK.prompt)
        + estimate_tokens(TASK.proposed_action)
    )
    assert needed == expected


def test_check_context_window_noop_when_model_has_no_known_limit():
    model = ScriptedAnsweringModel()
    assert model.context_window_tokens is None
    check_context_window(_grounding(10_000_000), TASK, model)  # must not raise


def test_check_context_window_passes_when_it_fits():
    model = _TinyWindowModel(context_window_tokens=1_000_000)
    check_context_window(_grounding(10), TASK, model)  # must not raise


def test_check_context_window_raises_when_it_does_not_fit():
    model = _TinyWindowModel(context_window_tokens=100)
    with pytest.raises(ContextWindowExceededError) as exc_info:
        check_context_window(_grounding(1000), TASK, model)
    assert exc_info.value.token_estimate > 0
    assert "context window" in str(exc_info.value)


def test_check_context_window_reserves_room_for_the_response():
    # Grounding alone fits under the raw limit, but not once the response
    # reserve is accounted for.
    limit = 200 + RESPONSE_RESERVE_TOKENS - 1
    model = _TinyWindowModel(context_window_tokens=limit)
    needed = context_window_needed(_grounding(0), TASK)
    with pytest.raises(ContextWindowExceededError):
        check_context_window(_grounding(limit - needed), TASK, model)


# --- Provider.respond() checks BEFORE calling the answering model -----------


def test_provider_respond_raises_before_calling_the_answering_model():
    model = _TinyWindowModel(context_window_tokens=1)
    provider = ContextDumpProvider(model)
    corpus = [CorpusArtifact(id="D-1", type="decision", path="d1.md", text="# D-1\n\nSome decision text.\n")]
    provider.prepare(corpus)
    with pytest.raises(ContextWindowExceededError):
        provider.respond(TASK)
    assert model.respond_calls == 0  # never reached the "API"


def test_provider_respond_succeeds_when_it_fits():
    model = _TinyWindowModel(context_window_tokens=1_000_000)
    provider = ContextDumpProvider(model)
    corpus = [CorpusArtifact(id="D-1", type="decision", path="d1.md", text="# D-1\n\nSome decision text.\n")]
    provider.prepare(corpus)
    provider.respond(TASK)
    assert model.respond_calls == 1


# --- reactive reclassification of a real backend's own rejection ------------


def test_reraise_if_context_length_reclassifies_matching_message():
    exc = RuntimeError("litellm gateway returned HTTP 400: maximum context length exceeded")
    with pytest.raises(ContextWindowExceededError) as exc_info:
        _reraise_if_context_length(exc, prompt_tokens=12345)
    assert exc_info.value.token_estimate == 12345


def test_reraise_if_context_length_does_not_misclassify_a_rate_limit_error():
    # "reduce your input length" is a rate-limit hint (TPM), not an overflow —
    # must NOT be reclassified as a benign, excluded-from-adherence outcome.
    exc = RuntimeError(
        "litellm gateway returned HTTP 429: Rate limit reached for requests, "
        "please reduce your input length or add delay between requests."
    )
    _reraise_if_context_length(exc, prompt_tokens=1)  # must not raise


def test_reraise_if_context_length_does_not_misclassify_a_tool_count_error():
    exc = RuntimeError(
        "litellm gateway returned HTTP 400: too many tokens in the tools "
        "array, max 128 tools allowed"
    )
    _reraise_if_context_length(exc, prompt_tokens=1)  # must not raise


def test_reraise_if_context_length_leaves_unrelated_errors_alone():
    exc = RuntimeError("litellm gateway returned HTTP 500: internal server error")
    _reraise_if_context_length(exc, prompt_tokens=1)  # must not raise


# --- runner.cli: a first-class outcome, not a generic error ------------------


def test_execute_runs_records_context_window_exceeded_distinctly(tmp_path):
    scenarios = load_scenarios(_SCENARIOS)
    sc = scenarios[0]
    model = _TinyWindowModel(context_window_tokens=1)
    partial = tmp_path / "run.partial.jsonl"

    results, errors = _execute_runs([("context_dump", sc)], model, 0, "local-hash", partial)

    assert not results
    assert len(errors) == 1
    assert errors[0]["kind"] == "context_window_exceeded"

    lines = [json.loads(line) for line in partial.read_text().splitlines()]
    assert lines[0]["record"] == "context_window_exceeded"
    assert lines[0]["kind"] == "context_window_exceeded"


def test_print_metrics_flags_context_exceeded_separately_from_errors(capsys):
    errors = [
        {"arm": "context_dump", "scenario_id": "s0", "error": "boom", "kind": "context_window_exceeded"},
        {"arm": "context_dump", "scenario_id": "s1", "error": "RuntimeError('transient')"},
    ]
    _print_metrics(results=[], errors=errors)
    out = capsys.readouterr()
    assert "context_dump" in out.out
    assert "0/2" in out.out
    assert "context window exceeded" in out.err
    assert "partial coverage" in out.err  # the generic-error cell still triggers this note


def test_write_report_tracks_n_context_exceeded_separately(tmp_path):
    errors = [
        {"arm": "context_dump", "scenario_id": "s0", "error": "boom", "kind": "context_window_exceeded"},
        {"arm": "context_dump", "scenario_id": "s1", "error": "boom2", "kind": "context_window_exceeded"},
        {"arm": "context_dump", "scenario_id": "s2", "error": "RuntimeError('transient')"},
    ]
    path = _write_report([], tmp_path, "test", errors)
    report = json.loads(path.read_text())
    d = report["metrics_by_arm"]["context_dump"]
    assert d["n_context_exceeded"] == 2
    assert d["n_errors"] == 1
    assert d["n_total"] == 3
    assert d["n_runs"] == 0


# --- scoring.metrics: n_context_exceeded is its own field --------------------


def test_aggregate_tracks_context_exceeded_apart_from_errors():
    m = aggregate("context_dump", [], n_errors=1, n_context_exceeded=3)
    assert m.n_errors == 1
    assert m.n_context_exceeded == 3
    assert m.n_total == 4
    d = m.as_dict()
    assert d["n_context_exceeded"] == 3


# --- scoring.crossover: the point excludes CWE cells, keeping the chart honest


def test_build_dataset_reports_none_adherence_when_every_cell_hits_the_ceiling(monkeypatch, tmp_path):
    import scoring.crossover as crossover
    from scoring.crossover import render_chart

    monkeypatch.setattr(
        crossover, "make_answering_model", lambda name, seed: _TinyWindowModel(context_window_tokens=1, seed=seed)
    )
    scenarios = load_scenarios(_SCENARIOS)
    ds = build_dataset(scenarios, arms=("context_dump",), ns=(3, 6), seed=0)

    for point in ds["arms"]["context_dump"]:
        assert point["adherence_rate"] is None  # not a misleading 0.0
        assert point["context_window_exceeded_count"] > 0
        assert point["context_window_exceeded_rate"] == 1.0

    kinds = {e.get("kind") for e in ds["errors"]}
    assert kinds == {"context_window_exceeded"}

    # The dataset must still be renderable — no crash on a None adherence_rate.
    render_chart(ds, tmp_path / "crossover")


def test_build_dataset_excludes_only_cwe_cells_when_partial(monkeypatch):
    import scoring.crossover as crossover

    # A window generous enough that the offline stub always fits (it never
    # calls a real backend, so any large limit works) — this exercises the
    # "no cells hit the ceiling" path stays exactly as before.
    monkeypatch.setattr(
        crossover, "make_answering_model",
        lambda name, seed: _TinyWindowModel(context_window_tokens=1_000_000, seed=seed),
    )
    scenarios = load_scenarios(_SCENARIOS)
    ds = build_dataset(scenarios, arms=("context_dump", "naive_rag"), ns=(3, 6), seed=0)
    for arm in ("context_dump", "naive_rag"):
        for point in ds["arms"][arm]:
            assert point["adherence_rate"] is not None
            assert point["context_window_exceeded_count"] == 0
            assert point["context_window_exceeded_rate"] == 0.0
    assert ds["errors"] == []


def test_multiseed_aggregation_carries_context_window_exceeded_fields(monkeypatch):
    # Regression: _AGG_FIELDS previously dropped context_window_exceeded_count
    # /_rate entirely once seeds were aggregated, even though cmd_demo points
    # users at exactly this field in the (possibly multi-seed) dataset.
    import scoring.crossover as crossover

    monkeypatch.setattr(
        crossover, "make_answering_model",
        lambda name, seed: _TinyWindowModel(context_window_tokens=1, seed=seed),
    )
    scenarios = load_scenarios(_SCENARIOS)
    from scoring.crossover import build_dataset_multiseed

    ds = build_dataset_multiseed(scenarios, arms=("context_dump",), ns=(3,), seeds=[0, 1])
    point = ds["arms"]["context_dump"][0]
    assert point["context_window_exceeded_count"] > 0
    assert point["context_window_exceeded_rate"] == 1.0
    assert point["n_seeds"] == 2


# --- coverage-flagging must recognize context-exceeded, not just errors -----


def test_report_coverage_flags_context_exceeded_arm_with_zero_errors():
    from scripts.report import _coverage, _leaderboard

    d = {
        "arm": "context_dump", "n_runs": 0, "n_errors": 0, "n_context_exceeded": 5,
        "n_total": 5, "adherence_rate": 0.0, "stale_decision_rate": 0.0,
        "false_permit_rate": 0.0, "false_prohibit_rate": 0.0, "governing_recall_rate": None,
    }
    assert _coverage(d) == "0/5*"
    md = _leaderboard({"metrics_by_arm": {"context_dump": d}})
    assert "partial coverage" in md


def test_dashboard_coverage_flags_context_exceeded_arm_with_zero_errors():
    from runner.dashboard import _coverage_cell, _metric_table

    d = {
        "arm": "context_dump", "n_runs": 0, "n_errors": 0, "n_context_exceeded": 5,
        "n_total": 5, "adherence_rate": 0.0, "stale_decision_rate": 0.0,
        "false_permit_rate": 0.0, "false_prohibit_rate": 0.0, "governing_recall_rate": None,
    }
    assert _coverage_cell(d) == "0/5*"
    table = _metric_table({"metrics_by_arm": {"context_dump": d}})
    assert "partial coverage" in table


def test_report_and_dashboard_coverage_unflagged_for_full_coverage():
    from runner.dashboard import _coverage_cell
    from scripts.report import _coverage

    d = {"n_runs": 3, "n_errors": 0, "n_context_exceeded": 0, "n_total": 3}
    assert _coverage(d) == "3/3"
    assert _coverage_cell(d) == "3/3"


# --- cmd_batch: the same symmetric preflight as every other entry point -----


def test_cmd_batch_skips_a_cell_that_exceeds_the_context_window(monkeypatch, tmp_path):
    import argparse

    import runner.cli as cli

    tiny_model = _TinyWindowModel(context_window_tokens=1)
    monkeypatch.setattr(cli, "_preflight", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_answering_model", lambda name, seed: tiny_model)

    class _FakeBatches:
        def create(self, requests):
            raise AssertionError("must not submit a batch when every cell exceeds the context window")

    class _FakeClient:
        messages = type("M", (), {"batches": _FakeBatches()})()

    tiny_model._ensure_client = lambda: _FakeClient()

    args = argparse.Namespace(
        arms="context_dump", answering="claude", embedder="local-hash",
        scenarios=str(_SCENARIOS), out=str(tmp_path), seed=0, poll=1,
    )
    rc = cli.cmd_batch(args)
    assert rc == 1  # partial coverage: nothing scored
