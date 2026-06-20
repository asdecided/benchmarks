"""Token-cost accounting: dollar math, the usage/estimate fallback, and per-arm
aggregation that feeds the cost section of the report."""

import pytest

from scoring.cost import (
    BATCH_DISCOUNT,
    cell_tokens,
    cost_by_arm,
    dollars,
    price_for,
)


def test_dollars_opus_rates_and_batch_discount():
    # Opus 4.8: $5 / 1M input, $25 / 1M output.
    assert dollars(1_000_000, 0, "claude-opus-4-8") == pytest.approx(5.0)
    assert dollars(0, 1_000_000, "claude-opus-4-8") == pytest.approx(25.0)
    full = dollars(200_000, 4_000, "claude-opus-4-8")
    batch = dollars(200_000, 4_000, "claude-opus-4-8", batch=True)
    assert batch == pytest.approx(full * BATCH_DISCOUNT)


def test_price_for_unknown_model_raises():
    with pytest.raises(KeyError):
        price_for("gpt-x")


def test_cell_tokens_prefers_real_usage_then_falls_back_to_estimate():
    real = {"usage": {"input_tokens": 1234, "output_tokens": 56}}
    assert cell_tokens(real) == (1234, 56, True)
    est = {"grounding": {"token_estimate": 800}}  # pre-usage-capture run
    assert cell_tokens(est) == (800, 0, False)


def _run(arm, model, *, usage=None, estimate=None):
    r = {"arm": arm, "answering_model": {"version": model}}
    if usage is not None:
        r["usage"] = usage
    if estimate is not None:
        r["grounding"] = {"token_estimate": estimate}
    return r


def test_cost_by_arm_separates_arms_and_marks_exactness():
    runs = [
        _run("context_dump", "claude-opus-4-8", usage={"input_tokens": 100_000, "output_tokens": 200}),
        _run("context_dump", "claude-opus-4-8", usage={"input_tokens": 120_000, "output_tokens": 200}),
        _run("rac", "claude-opus-4-8", usage={"input_tokens": 2_000, "output_tokens": 200}),
    ]
    by = cost_by_arm(runs)
    assert by["context_dump"]["n"] == 2
    assert by["context_dump"]["input_tokens_total"] == 220_000
    assert by["context_dump"]["input_tokens_mean"] == 110_000
    # context_dump should cost far more than rac (it pastes the whole corpus).
    assert by["context_dump"]["usd_total"] > by["rac"]["usd_total"]
    assert by["context_dump"]["exact"] and by["rac"]["exact"]
    # batch halves the dollar figure.
    assert cost_by_arm(runs, batch=True)["rac"]["usd_total"] == pytest.approx(
        by["rac"]["usd_total"] * BATCH_DISCOUNT
    )


def test_cost_by_arm_marks_inexact_on_estimate_fallback():
    runs = [_run("naive_rag", "claude-opus-4-8", estimate=1500)]
    by = cost_by_arm(runs)
    assert by["naive_rag"]["input_tokens_total"] == 1500
    assert by["naive_rag"]["exact"] is False  # fell back to the estimate
