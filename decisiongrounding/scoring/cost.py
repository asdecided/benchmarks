"""Token-cost accounting for the answering model.

The arms differ enormously in how much they put in front of the held-constant
answering model: context_dump pastes the whole corpus (input tokens scale with
N), while naive_rag and rac send a small retrieved/assembled slice. So token
cost is a first-class axis of the benchmark, not an afterthought — a grounding
strategy that matches adherence at a fraction of the tokens is the better one.

Prices are USD per 1,000,000 tokens (input, output), from Anthropic's published
pricing. The Batch API bills at 50% of standard. Embedding cost (Voyage) is a
one-time prepare-time charge that is negligible next to the per-cell answering
calls and is reported separately when relevant.
"""

from __future__ import annotations

# (input $/1M, output $/1M) at standard rates.
PRICES: dict[str, tuple[float, float]] = {
    "claude-opus-4-8": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5": (1.0, 5.0),
}

BATCH_DISCOUNT = 0.5  # Batch API = 50% of standard price.


def price_for(model: str) -> tuple[float, float]:
    """(input, output) $/1M for a pinned model id; raises on an unknown id so a
    report never silently invents a price."""
    try:
        return PRICES[model]
    except KeyError as exc:
        raise KeyError(
            f"no published price for model {model!r}; add it to scoring.cost.PRICES"
        ) from exc


def dollars(input_tokens: int, output_tokens: int, model: str, *, batch: bool = False) -> float:
    """USD for one answering call. With batch=True, applies the 50% discount."""
    in_rate, out_rate = price_for(model)
    cost = (input_tokens * in_rate + output_tokens * out_rate) / 1_000_000
    return cost * (BATCH_DISCOUNT if batch else 1.0)


def cell_tokens(run: dict) -> tuple[int, int, bool]:
    """(input_tokens, output_tokens, exact) for one run record. Prefers the real
    API `usage`; falls back to the deterministic grounding `token_estimate` for
    input (output unknown -> 0) when a run predates usage capture. The bool flags
    whether the figure is measured (True) or estimated (False)."""
    usage = run.get("usage")
    if usage:
        return int(usage["input_tokens"]), int(usage["output_tokens"]), True
    est = (run.get("grounding") or {}).get("token_estimate", 0)
    return int(est), 0, False


def cost_by_arm(runs: list[dict], *, batch: bool = False) -> dict[str, dict]:
    """Per-arm token + dollar totals/means over a list of run records.

    Returns {arm: {n, input_tokens_total, output_tokens_total,
    input_tokens_mean, output_tokens_mean, usd_total, usd_mean, exact}}.
    `exact` is False when any cell fell back to the token estimate."""
    by_arm: dict[str, list[dict]] = {}
    for r in runs:
        by_arm.setdefault(r["arm"], []).append(r)

    out: dict[str, dict] = {}
    for arm, rs in by_arm.items():
        ti = to = 0
        usd = 0.0
        exact = True
        for r in rs:
            inp, outp, is_exact = cell_tokens(r)
            exact = exact and is_exact
            ti += inp
            to += outp
            model = (r.get("answering_model") or {}).get("version", "")
            try:
                usd += dollars(inp, outp, model, batch=batch)
            except KeyError:
                exact = False  # unknown price -> dollars omitted, mark inexact
        n = len(rs)
        out[arm] = {
            "n": n,
            "input_tokens_total": ti,
            "output_tokens_total": to,
            "input_tokens_mean": ti / n if n else 0,
            "output_tokens_mean": to / n if n else 0,
            "usd_total": usd,
            "usd_mean": usd / n if n else 0,
            "exact": exact,
        }
    return out
