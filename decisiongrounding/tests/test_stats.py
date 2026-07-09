"""Paired-significance statistics: exact known-value fixtures, determinism, and
the committed real headline record. Dependency-free (no SciPy)."""

import json
import random
from pathlib import Path

import pytest

from scoring.stats import (
    binom_two_sided_p,
    collect_pairs,
    mcnemar_exact,
    pair_stats,
    paired_odds_ratio,
    paired_significance,
    paired_table,
    records_from_runs,
    risk_difference,
    stats_by_n,
    wilson_ci,
)

_ROOT = Path(__file__).resolve().parent.parent
_HEADLINE = _ROOT / "results" / "published" / "2026-06-20-headline-opus-4-8-voyage.json"
_STATS_SCHEMA = _ROOT / "schema" / "paired_stats.schema.json"


# --- exact known values -------------------------------------------------------


def test_binom_two_sided_p_known_values():
    # k=1, n=9 under p=0.5: 2 * (C(9,0) + C(9,1)) / 2^9 = 20/512
    assert binom_two_sided_p(1, 9) == 20 / 512
    # symmetric: k and n-k give the same p
    assert binom_two_sided_p(8, 9) == 20 / 512
    # even split doubles past 1.0 and clamps
    assert binom_two_sided_p(5, 10) == 1.0
    assert binom_two_sided_p(0, 0) == 1.0


def test_mcnemar_exact_known_value():
    m = mcnemar_exact(1, 8)
    assert m["statistic"] == 1
    assert m["n_discordant"] == 9
    assert m["p_value"] == 0.0390625  # 20/512 exactly
    assert "degenerate" not in m


def test_mcnemar_exact_headline_shape():
    # The committed real headline: rac adherent on 18/19 where no_grounding
    # fails on all — b=18, c=0 -> p = 2 / 2^18.
    m = mcnemar_exact(18, 0)
    assert m["p_value"] == 2 / 2**18


def test_mcnemar_degenerate_no_discordance():
    m = mcnemar_exact(0, 0)
    assert m["p_value"] == 1.0
    assert m["degenerate"] is True


def test_wilson_ci_known_value():
    lo, hi = wilson_ci(8, 10)
    assert lo == pytest.approx(0.4902, abs=1e-3)
    assert hi == pytest.approx(0.9433, abs=1e-3)
    assert lo < 0.8 < hi
    assert wilson_ci(0, 0) == (0.0, 1.0)  # uninformative, never a crash
    lo0, hi0 = wilson_ci(0, 10)
    assert lo0 == 0.0 and 0.0 < hi0 < 0.35


def test_risk_difference_known_value():
    rd = risk_difference(3, 1, 10)
    assert rd["diff"] == pytest.approx(0.2)
    # paired Wald SE = sqrt(b + c - (b-c)^2/n)/n = sqrt(3.6)/10
    half = 1.96 * (3.6**0.5) / 10
    assert rd["ci"][0] == pytest.approx(0.2 - half)
    assert rd["ci"][1] == pytest.approx(0.2 + half)
    assert risk_difference(0, 0, 0)["degenerate"] is True


def test_risk_difference_ci_is_clamped_to_parameter_space():
    # b=9,c=0,n=10: diff=0.9, Wald upper = 0.9 + 1.96*sqrt(0.9)/10 ~= 1.086 -> clip to 1.
    hi = risk_difference(9, 0, 10)
    assert hi["diff"] == pytest.approx(0.9)
    assert hi["ci"][1] == 1.0 and hi["ci"][0] >= -1.0
    # symmetric: lower bound clips to -1.
    lo = risk_difference(0, 9, 10)
    assert lo["ci"][0] == -1.0 and lo["ci"][1] <= 1.0


def test_paired_odds_ratio_zero_cell_is_degenerate_not_fudged():
    orr = paired_odds_ratio(5, 0)
    assert orr["or"] is None and orr["ci"] is None and orr["degenerate"] is True
    orr = paired_odds_ratio(3, 1)
    assert orr["or"] == 3.0
    assert orr["ci"][0] < 3.0 < orr["ci"][1]


def test_paired_table_counts():
    pairs = [(True, True), (True, False), (True, False), (False, True), (False, False)]
    assert paired_table(pairs) == (1, 2, 1, 1)


# --- joining and end-to-end ---------------------------------------------------


def _designed_records():
    """rac adherent on s01..s08; naive_rag on s01..s05 and s09.
    Table: a=5 (s01-s05), b=3 (s06-s08), c=1 (s09), d=1 (s10)."""
    recs = []
    for i in range(1, 11):
        sid = f"s{i:02d}"
        recs.append({"arm": "rac", "scenario_id": sid, "adherent": i <= 8})
        recs.append({"arm": "naive_rag", "scenario_id": sid, "adherent": i <= 5 or i == 9})
    return recs


def test_pair_stats_on_designed_table():
    pairs = collect_pairs(_designed_records(), "rac", "naive_rag")
    st = pair_stats(pairs, "rac", "naive_rag")
    assert st["table"] == [5, 3, 1, 1]
    assert st["n_pairs"] == 10
    assert st["rate_a"] == pytest.approx(0.8)
    assert st["rate_b"] == pytest.approx(0.6)
    # b=3, c=1 -> exact two-sided binomial p at min(3,1)=1 of 4: 10/16
    assert st["mcnemar"]["p_value"] == 10 / 16
    assert st["risk_difference"]["diff"] == pytest.approx(0.2)


def test_collect_pairs_is_order_independent():
    recs = _designed_records()
    shuffled = list(recs)
    random.Random(0).shuffle(shuffled)
    assert paired_significance(recs) == paired_significance(shuffled)


def test_collect_pairs_joins_on_seed_and_n_and_example_id():
    recs = [
        {"arm": "rac", "example_id": "e1", "seed": 0, "N": 50, "passed": True},
        {"arm": "no_grounding", "example_id": "e1", "seed": 0, "N": 50, "passed": False},
        # different seed: must not pair with seed 0
        {"arm": "rac", "example_id": "e1", "seed": 1, "N": 50, "passed": False},
    ]
    pairs = collect_pairs(recs, "rac", "no_grounding", outcome="passed")
    assert pairs == [(True, False)]


def test_paired_significance_skips_absent_arms():
    out = paired_significance(_designed_records())
    assert set(out["pairs"]) == {"rac_vs_naive_rag"}
    assert out["outcome"] == "adherent"


def test_stats_by_n_groups_cells():
    cells = []
    for n in (10, 300):
        for i in range(4):
            sid = f"s{i}"
            # rac always adherent; naive_rag only at N=10
            cells.append({"seed": 0, "N": n, "arm": "rac", "scenario_id": sid, "adherent": True})
            cells.append({"seed": 0, "N": n, "arm": "naive_rag", "scenario_id": sid,
                          "adherent": n == 10})
    out = stats_by_n(cells)
    assert set(out) == {10, 300}
    assert out[10]["pairs"]["rac_vs_naive_rag"]["mcnemar"]["degenerate"] is True
    top = out[300]["pairs"]["rac_vs_naive_rag"]
    assert top["table"] == [0, 4, 0, 0]
    assert top["mcnemar"]["p_value"] == 2 / 2**4


# --- the committed real headline record ---------------------------------------


def test_headline_record_reproduces_preregistered_shape():
    report = json.loads(_HEADLINE.read_text())
    records = records_from_runs(report["runs"])
    out = paired_significance(records)
    # rac vs no_grounding: rac adherent 18/19, no_grounding 0/19 -> b=18, c=0.
    vs_none = out["pairs"]["rac_vs_no_grounding"]
    assert vs_none["table"] == [0, 18, 0, 1]
    assert vs_none["mcnemar"]["p_value"] == 2 / 2**18
    # rac vs naive_rag tie at base N (the expected-tie regime): no discordance.
    vs_rag = out["pairs"]["rac_vs_naive_rag"]
    assert vs_rag["mcnemar"]["degenerate"] is True
    assert vs_rag["table"][1] == 0 and vs_rag["table"][2] == 0


def test_paired_significance_validates_against_schema():
    try:
        import jsonschema  # type: ignore
    except ImportError:
        pytest.skip("jsonschema not installed")
    out = paired_significance(_designed_records())
    jsonschema.validate(out, json.loads(_STATS_SCHEMA.read_text()))
    report = json.loads(_HEADLINE.read_text())
    real = paired_significance(records_from_runs(report["runs"]))
    jsonschema.validate(real, json.loads(_STATS_SCHEMA.read_text()))


# --- crossover integration ----------------------------------------------------


def test_offline_crossover_carries_cells_and_stats_deterministically():
    from scenarios.loader import load_scenarios
    from scoring.crossover import build_dataset

    scenarios = load_scenarios(_ROOT / "scenarios")
    kwargs = dict(arms=("context_dump", "naive_rag"), ns=(10, 50), seed=0)
    ds1 = build_dataset(scenarios, **kwargs)
    ds2 = build_dataset(scenarios, **kwargs)
    assert ds1["cells"], "crossover datasets must retain per-cell booleans"
    assert all({"seed", "N", "arm", "scenario_id", "adherent"} <= set(c) for c in ds1["cells"])
    assert ds1["stats"] is not None
    assert set(ds1["stats"]) == {10, 50}
    assert json.dumps(ds1["stats"], sort_keys=True) == json.dumps(ds2["stats"], sort_keys=True)


def test_multiseed_crossover_pairs_by_scenario_and_seed():
    from scenarios.loader import load_scenarios
    from scoring.crossover import DISCRIMINATING, build_dataset_multiseed

    scenarios = load_scenarios(_ROOT / "scenarios")
    n_disc = len([s for s in scenarios if s.scenario_type in DISCRIMINATING])
    ds = build_dataset_multiseed(
        scenarios, arms=("context_dump", "naive_rag"), ns=(10,), seeds=(0, 1))
    assert len(ds["cells"]) == 2 * 2 * n_disc  # seeds x arms x scenarios
    block = ds["stats"][10]["pairs"]["context_dump_vs_naive_rag"]
    assert block["n_pairs"] == 2 * n_disc  # scenario x seed pairs


def test_merge_with_legacy_dataset_degrades_stats_to_none():
    from scenarios.loader import load_scenarios
    from scoring.crossover import build_dataset, merge_seed_datasets

    scenarios = load_scenarios(_ROOT / "scenarios")
    arms, ns = ("context_dump", "naive_rag"), (10,)
    legacy = build_dataset(scenarios, arms=arms, ns=ns, seed=0)
    legacy.pop("cells")  # a dataset produced before per-cell retention
    legacy.pop("stats")
    new = build_dataset(scenarios, arms=arms, ns=ns, seed=1)
    merged = merge_seed_datasets(legacy, [(1, new)], list(arms), list(ns),
                                 ("rac", "naive_rag"))
    assert merged["cells"] is None
    assert merged["stats"] is None


def test_merge_extends_cells_and_recomputes_stats():
    from scenarios.loader import load_scenarios
    from scoring.crossover import build_dataset, merge_seed_datasets

    scenarios = load_scenarios(_ROOT / "scenarios")
    arms, ns = ("context_dump", "naive_rag"), (10,)
    first = build_dataset(scenarios, arms=arms, ns=ns, seed=0)
    second = build_dataset(scenarios, arms=arms, ns=ns, seed=1)
    merged = merge_seed_datasets(first, [(1, second)], list(arms), list(ns),
                                 ("rac", "naive_rag"))
    assert len(merged["cells"]) == len(first["cells"]) + len(second["cells"])
    block = merged["stats"][10]["pairs"]["context_dump_vs_naive_rag"]
    assert block["n_pairs"] == len(merged["cells"]) // 2
