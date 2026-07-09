"""Paired-significance statistics for the publication study (SWE-DecisionBench).

Exact McNemar tests, Wilson intervals, and paired effect sizes over
per-(scenario, arm) boolean outcomes. Pre-registered in
`spec/analysis-plan-amendment-1.md`.

This is an *analysis* layer: it consumes deterministic scores downstream and
never enters the scored or gated path (ADR-066 / ADR-097 posture — the
headline stays a single legible rate; these are the inferential statistics the
paper reports alongside it). Everything here is a pure function of its inputs:
stdlib-only (`math.comb`), no SciPy, no randomness, no clock — the same
records always produce byte-identical statistics.
"""

from __future__ import annotations

Z95 = 1.96  # two-sided 95% normal critical value, matching metrics._T95's df>=30 tail

# The pre-registered confirmatory pair is rac vs naive_rag (the retrieval
# thesis); the rest are reported context. When `pairs` is not given explicitly,
# every pair of arms present is computed — deterministic, and the analysis plan
# pins which pair carries the confirmatory weight.
CONFIRMATORY_PAIR = ("rac", "naive_rag")

# The pre-registered H1 family (spec/analysis-plan-amendment-1.md): the
# confirmatory test is rac-vs-naive_rag adherence at N=300, reported
# UNcorrected; the secondary cells at N in {50, 150} of the same pair/outcome
# are Holm-corrected; N=10 is descriptive and everything else is exploratory,
# reported raw and labelled as such.
CONFIRMATORY_OUTCOME = "adherent"
CONFIRMATORY_N = 300
SECONDARY_NS = (50, 150)

# Join fields for pairing records across arms. `example_id` is the alias the
# gitchameleon resolution records use for `scenario_id`; `seed` and `N` scope
# crossover cells so a pair is always the same scenario under the same
# conditions.
_JOIN_FIELDS = ("scenario_id", "example_id", "seed", "N")


def binom_two_sided_p(k: int, n: int) -> float:
    """Exact two-sided binomial p-value for `k` successes in `n` trials under
    p = 0.5: twice the smaller tail, clamped to 1.0. Returns 1.0 for n == 0
    (no evidence either way)."""
    if n <= 0:
        return 1.0
    from math import comb

    k = min(k, n - k)
    tail = sum(comb(n, i) for i in range(k + 1)) / 2**n
    return min(1.0, 2.0 * tail)


def mcnemar_exact(b: int, c: int) -> dict:
    """Exact McNemar test on the discordant counts of a paired 2x2 table.

    `b` = pairs where the first arm succeeded and the second failed; `c` = the
    reverse. Only discordant pairs carry information; the exact binomial
    (b + c trials at p = 0.5) replaces the chi-square approximation, so small
    studies need no continuity fudge. `degenerate` flags b + c == 0 (the arms
    never disagreed — e.g. the base-N tie) where the test is uninformative.
    """
    n = b + c
    out = {
        "b": b,
        "c": c,
        "n_discordant": n,
        "statistic": min(b, c),
        "p_value": binom_two_sided_p(min(b, c), n),
        "method": "mcnemar-exact-binomial",
    }
    if n == 0:
        out["degenerate"] = True
    return out


def wilson_ci(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    """Wilson score interval for a binomial proportion. For n == 0 the interval
    is the uninformative (0, 1)."""
    if n <= 0:
        return (0.0, 1.0)
    p = successes / n
    denom = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / denom
    half = (z / denom) * ((p * (1 - p) / n + z**2 / (4 * n**2)) ** 0.5)
    return (max(0.0, centre - half), min(1.0, centre + half))


def paired_table(pairs: list[tuple[bool, bool]]) -> tuple[int, int, int, int]:
    """(a, b, c, d) counts of a paired 2x2 table: a = both succeed, b = first
    only, c = second only, d = both fail."""
    a = b = c = d = 0
    for x, y in pairs:
        if x and y:
            a += 1
        elif x:
            b += 1
        elif y:
            c += 1
        else:
            d += 1
    return a, b, c, d


def risk_difference(b: int, c: int, n: int) -> dict:
    """Paired risk difference (first minus second arm) with a Wald 95% CI.

    d = (b - c) / n over all n pairs; the paired SE uses only the discordant
    structure: sqrt(b + c - (b - c)^2 / n) / n.

    A risk difference is bounded [-1, 1], but the Wald interval is a normal
    approximation that can spill past that (e.g. b large, c = 0, small n). The
    CI is clipped to the parameter space so it never reports an impossible
    rate difference.
    """
    if n <= 0:
        return {"diff": 0.0, "ci": [0.0, 0.0], "degenerate": True}
    diff = (b - c) / n
    se = ((b + c - (b - c) ** 2 / n) ** 0.5) / n
    return {"diff": diff, "ci": [max(-1.0, diff - Z95 * se), min(1.0, diff + Z95 * se)]}


def paired_odds_ratio(b: int, c: int) -> dict:
    """Conditional (paired) odds ratio b / c with a 95% CI obtained by
    transforming the Wilson interval on p = b / (b + c) via p / (1 - p).

    A zero discordant cell makes the ratio unbounded or zero; that is reported
    as `degenerate` with a null estimate rather than smoothed with a Haldane
    correction — the raw counts are alongside for the reader.
    """
    if b == 0 or c == 0:
        return {"or": None, "ci": None, "degenerate": True}
    lo_p, hi_p = wilson_ci(b, b + c)
    return {"or": b / c, "ci": [lo_p / (1 - lo_p), hi_p / (1 - hi_p)]}


def _join_key(rec: dict) -> tuple:
    sid = rec.get("scenario_id", rec.get("example_id"))
    return (sid, rec.get("seed"), rec.get("N"))


def collect_pairs(
    records: list[dict],
    arm_a: str,
    arm_b: str,
    *,
    outcome: str = "adherent",
) -> list[tuple[bool, bool]]:
    """Join per-record boolean outcomes into (arm_a, arm_b) pairs.

    Records are dicts carrying `arm`, an outcome boolean under `outcome`, and a
    join identity: `scenario_id` (or `example_id`), plus `seed` / `N` when the
    run sweeps them. Only keys present in *both* arms pair up. The output is
    sorted by join key, so shuffled input produces identical statistics.
    """
    sides: dict[tuple, dict[str, bool]] = {}
    for rec in records:
        if rec.get("arm") not in (arm_a, arm_b) or outcome not in rec:
            continue
        sides.setdefault(_join_key(rec), {})[rec["arm"]] = bool(rec[outcome])
    return [
        (sides[k][arm_a], sides[k][arm_b])
        for k in sorted(sides, key=repr)
        if arm_a in sides[k] and arm_b in sides[k]
    ]


def pair_stats(pairs: list[tuple[bool, bool]], label_a: str, label_b: str) -> dict:
    """The full pre-registered statistics block for one arm pair."""
    a, b, c, d = paired_table(pairs)
    n = a + b + c + d
    return {
        "arms": [label_a, label_b],
        "n_pairs": n,
        "table": [a, b, c, d],
        "rate_a": (a + b) / n if n else 0.0,
        "rate_a_ci": list(wilson_ci(a + b, n)),
        "rate_b": (a + c) / n if n else 0.0,
        "rate_b_ci": list(wilson_ci(a + c, n)),
        "mcnemar": mcnemar_exact(b, c),
        "risk_difference": risk_difference(b, c, n),
        "odds_ratio": paired_odds_ratio(b, c),
    }


def _all_pairs(arms_seen: set[str]) -> tuple[tuple[str, str], ...]:
    """Every pair of arms present, deterministically ordered, oriented with
    `rac` first where it appears (the direction the hypotheses are stated in)."""
    from itertools import combinations

    out = []
    for a, b in combinations(sorted(a for a in arms_seen if a), 2):
        out.append((b, a) if b == "rac" else (a, b))
    return tuple(out)


def paired_significance(
    records: list[dict],
    *,
    outcome: str = "adherent",
    pairs: tuple[tuple[str, str], ...] | None = None,
) -> dict:
    """Paired significance across arm pairs over shared scenarios.

    Returns {"outcome", "pairs": {"<a>_vs_<b>": pair_stats, ...}}; arm pairs
    with no shared records are omitted rather than reported as empty. When
    `pairs` is None, every pair of arms present is computed.
    """
    arms_seen = {rec.get("arm") for rec in records}
    if pairs is None:
        pairs = _all_pairs(arms_seen)
    out: dict = {"outcome": outcome, "pairs": {}}
    for arm_a, arm_b in pairs:
        if arm_a not in arms_seen or arm_b not in arms_seen:
            continue
        joined = collect_pairs(records, arm_a, arm_b, outcome=outcome)
        if joined:
            out["pairs"][f"{arm_a}_vs_{arm_b}"] = pair_stats(joined, arm_a, arm_b)
    return out


def stats_by_n(
    cells: list[dict],
    *,
    outcome: str = "adherent",
    pairs: tuple[tuple[str, str], ...] | None = None,
) -> dict:
    """Per-N paired significance over crossover cells ({seed, N, arm,
    scenario_id, adherent} records). The paired unit is scenario x seed —
    common random numbers, as pre-registered."""
    by_n: dict[int, list[dict]] = {}
    for cell in cells:
        by_n.setdefault(cell["N"], []).append(cell)
    return {
        n: paired_significance(by_n[n], outcome=outcome, pairs=pairs)
        for n in sorted(by_n)
    }


def holm_adjust(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni step-down adjusted p-values, returned in input order.

    Controls the family-wise error rate across `m = len(pvalues)` tests with no
    independence assumption. The k-th smallest raw p (k = 1..m) is scaled by
    (m - k + 1); a running maximum keeps the adjusted sequence monotonic and
    each value is capped at 1. `m <= 1` returns the inputs unchanged (nothing
    to correct). Pure and deterministic.
    """
    m = len(pvalues)
    if m <= 1:
        return [min(1.0, p) for p in pvalues]
    order = sorted(range(m), key=lambda i: pvalues[i])
    adj = [0.0] * m
    running = 0.0
    for rank, idx in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[idx]))
        adj[idx] = running
    return adj


def annotate_holm_family(stats_by_n_result: dict) -> None:
    """Tag the pre-registered H1 family in a crossover `stats` block, in place.

    For the confirmatory pair/outcome (rac vs naive_rag, adherent), the cells
    at `SECONDARY_NS` get a Holm-adjusted `p_value_holm` (Holm across whichever
    of {50, 150} are present) and `family = "secondary"`; the `CONFIRMATORY_N`
    cell is tagged `family = "confirmatory"` and left UNcorrected — the single
    pre-registered primary test. Every other cell is untouched (exploratory,
    reported raw and labelled). See spec/analysis-plan-amendment-1.md.
    """
    key = f"{CONFIRMATORY_PAIR[0]}_vs_{CONFIRMATORY_PAIR[1]}"

    def _mcnemar_at(n: int) -> dict | None:
        block = stats_by_n_result.get(n)
        if not block or block.get("outcome") != CONFIRMATORY_OUTCOME:
            return None
        return (block.get("pairs") or {}).get(key, {}).get("mcnemar")

    secondary = [mc for mc in (_mcnemar_at(n) for n in SECONDARY_NS) if mc is not None]
    if secondary:
        for mc, adj in zip(secondary, holm_adjust([mc["p_value"] for mc in secondary])):
            mc["p_value_holm"] = adj
            mc["family"] = "secondary"
    conf = _mcnemar_at(CONFIRMATORY_N)
    if conf is not None:
        conf["family"] = "confirmatory"


def records_from_runs(runs: list[dict], *, outcome: str = "adherent") -> list[dict]:
    """Flatten run-report entries (runner/cli.py `runs`) into stats records."""
    return [
        {
            "arm": r["arm"],
            "scenario_id": r["scenario_id"],
            outcome: bool(r["score"][outcome]),
        }
        for r in runs
        if "score" in r and outcome in r["score"]
    ]
