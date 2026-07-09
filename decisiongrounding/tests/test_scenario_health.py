"""scenario_health: per-scenario discrimination/validity classification."""

from scoring.health import scenario_health


def _rec(n, adherent):
    return {"N": n, "adherent": adherent}


def _dataset(per_scenario):
    return {"per_scenario": per_scenario}


def test_discriminating_scenario():
    # ceiling adheres, floor fails, arms separate.
    ds = _dataset({
        "context_dump": {"s": [_rec(10, 1.0), _rec(300, 1.0)]},
        "naive_rag": {"s": [_rec(10, 1.0), _rec(300, 0.0)]},
        "no_grounding": {"s": [_rec(10, 0.0), _rec(300, 0.0)]},
    })
    h = scenario_health(ds)
    assert h["counts"]["discriminating"] == 1
    row = h["scenarios"][0]
    assert row["class"] == "discriminating" and row["separates"] is True
    assert row["max_gap"] == 1.0


def test_broken_scenario_ceiling_never_adheres():
    ds = _dataset({
        "context_dump": {"s": [_rec(10, 0.0), _rec(300, 0.0)]},
        "no_grounding": {"s": [_rec(10, 0.0), _rec(300, 0.0)]},
    })
    h = scenario_health(ds)
    assert h["scenarios"][0]["class"] == "broken"
    assert h["counts"]["broken"] == 1


def test_contaminated_scenario_floor_adheres():
    # ceiling adheres AND floor also adheres -> parametric memory suffices.
    ds = _dataset({
        "context_dump": {"s": [_rec(10, 1.0)]},
        "no_grounding": {"s": [_rec(10, 1.0)]},
    })
    h = scenario_health(ds)
    assert h["scenarios"][0]["class"] == "contaminated"


def test_tie_scenario_no_separation():
    # Ceiling adheres, no floor arm to separate from, and the present arms
    # never differ -> no between-arm signal.
    ds = _dataset({
        "context_dump": {"s": [_rec(10, 1.0), _rec(300, 1.0)]},
        "naive_rag": {"s": [_rec(10, 1.0), _rec(300, 1.0)]},
    })
    h = scenario_health(ds)
    assert h["scenarios"][0]["class"] == "tie"
    assert h["scenarios"][0]["separates"] is False


def test_unknown_without_control_arms():
    ds = _dataset({
        "rac": {"s": [_rec(10, 1.0)]},
        "naive_rag": {"s": [_rec(10, 0.0)]},
    })
    h = scenario_health(ds)
    assert h["scenarios"][0]["class"] == "unknown"
    assert h["controls"] == {"ceiling": False, "floor": False}


def test_multi_seed_fractions_and_summary_counts():
    ds = _dataset({
        "context_dump": {"good": [_rec(300, 1.0)], "bad": [_rec(300, 0.0)]},
        "naive_rag": {"good": [_rec(300, 0.4)], "bad": [_rec(300, 0.0)]},
        "no_grounding": {"good": [_rec(300, 0.0)], "bad": [_rec(300, 0.0)]},
    })
    h = scenario_health(ds)
    assert h["total"] == 2
    classes = {s["scenario_id"]: s["class"] for s in h["scenarios"]}
    assert classes["good"] == "discriminating"   # ceiling 1.0, floor 0, gap 0.6
    assert classes["bad"] == "broken"            # ceiling never adheres


def test_legacy_dataset_without_per_scenario():
    h = scenario_health({})
    assert h["total"] == 0 and h["scenarios"] == []
