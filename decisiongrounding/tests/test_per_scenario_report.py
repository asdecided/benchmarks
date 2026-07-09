"""report.py per-scenario failure attribution: surfaces when one scenario
dominates an arm's failures (the pilot's 12-of-13 diagnosis)."""

from scripts.report import _per_scenario_section


def _cell(n, adherent):
    return {"N": n, "adherent": adherent, "stale_decision_followed": False,
            "governing_decision_retrieved": True}


def test_concentrated_failure_triggers_headline():
    # one scenario holds 3 of 4 of the arm's failures
    dataset = {
        "per_scenario": {
            "rac": {
                "dominant": [_cell(10, False), _cell(50, False), _cell(150, False)],
                "other": [_cell(10, True), _cell(50, False)],
                "clean": [_cell(10, True), _cell(50, True)],
            }
        }
    }
    out = "\n".join(_per_scenario_section(dataset))
    assert "Per-scenario failure attribution" in out
    assert "3 of 4" in out and "dominant" in out
    assert "rests" in out  # the concentration warning


def test_spread_failures_no_headline():
    dataset = {
        "per_scenario": {
            "rac": {
                "a": [_cell(10, False)],
                "b": [_cell(10, False)],
                "c": [_cell(10, True)],
            }
        }
    }
    out = "\n".join(_per_scenario_section(dataset))
    assert "come from a single scenario" not in out


def test_no_failures_reported_cleanly():
    dataset = {"per_scenario": {"rac": {"a": [_cell(10, True)]}}}
    out = "\n".join(_per_scenario_section(dataset))
    assert "no failures" in out


def test_legacy_dataset_without_per_scenario_renders_nothing():
    assert _per_scenario_section({}) == []
