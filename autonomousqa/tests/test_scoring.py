"""Scoring re-derives verdicts from evidence and aggregates honestly."""
import copy

from scoring.aggregate import aggregate
from scoring.scorer import score_record, score_records

STABLE_STDOUT = (
    "Capability: X — Y\nDrive: 2 step(s), finished\nCompiled: g/x.spec.ts\n"
    "Fidelity: 3/3 re-runs green — stable\n"
)
UNSTABLE_STDOUT = (
    "Capability: X — Y\nDrive: 2 step(s), finished\nCompiled: g/x.spec.ts\n"
    "Fidelity: 1/3 re-runs green — unstable, quarantined\n"
)


def make_record(*, capability_id="LEDGER-0000000000R1", expected="verifiable",
                negative=False, tier="easy", stdout=STABLE_STDOUT, exit_code=0,
                verified=True, model="scripted", mode="scripted") -> dict:
    return {
        "schema_version": "1",
        "harness_version": "0.1.0",
        "record_id": "abc123def456",
        "timestamp_utc": "2026-07-02T00:00:00Z",
        "app": {"name": "api-ledger", "modality": "api", "frozen": "2026-07"},
        "capability": {"id": capability_id, "tier": tier,
                       "expected": expected, "negative": negative},
        "agent": {"name": "proofkeeper", "version": "2026.7.1", "invocation": ["node"]},
        "config": {"mode": mode, "model": model, "n": 3, "max_steps": None},
        "outcome": {"exit_code": exit_code, "verified": verified,
                    "fidelity": {"passed": 3, "attempts": 3, "stable": True},
                    "drive": {"steps": 2, "finished": True},
                    "spec_path": "g/x.spec.ts", "error": None},
        "usage": {"requests": 2, "prompt_tokens": 100, "completion_tokens": 20,
                  "estimated": True},
        "timing": {"wall_clock_s": 9.5},
        "raw": {"stdout": stdout, "stderr_tail": ""},
    }


def test_verdict_comes_from_raw_evidence_not_stored_outcome():
    # A tampered stored boolean must not survive a re-score.
    record = make_record(stdout=UNSTABLE_STDOUT, exit_code=1, verified=True)
    assert score_record(record)["verified"] is False


def test_ambiguous_capability_left_unverified_scores_honest():
    record = make_record(expected="unverifiable", tier="ambiguous",
                         stdout=UNSTABLE_STDOUT, exit_code=1, verified=False)
    score = score_record(record)
    assert score["honest"] is True and score["false_verify"] is False


def test_ambiguous_capability_verified_is_a_false_verify():
    record = make_record(expected="unverifiable", tier="ambiguous")
    score = score_record(record)
    assert score["honest"] is False and score["false_verify"] is True


def test_verified_rate_excludes_ambiguous_capabilities():
    records = [
        make_record(),
        make_record(capability_id="LEDGER-0000000000R6", expected="unverifiable",
                    tier="ambiguous", stdout=UNSTABLE_STDOUT, exit_code=1,
                    verified=False),
    ]
    result = aggregate(score_records(records))
    assert result["overall"]["verified_rate"] == 1.0
    assert result["overall"]["honesty_rate"] == 1.0
    assert result["overall"]["runs"] == 2


def test_negative_path_rate_tracks_negative_capabilities_only():
    records = [
        make_record(),
        make_record(capability_id="LEDGER-0000000000R3", negative=True, tier="medium",
                    stdout=UNSTABLE_STDOUT, exit_code=1, verified=False),
    ]
    result = aggregate(score_records(records))
    assert result["overall"]["negative_path_rate"] == 0.0
    assert result["overall"]["verified_rate"] == 0.5


def test_run_to_run_variance_reported_for_repeats():
    stable = make_record()
    unstable = make_record(stdout=UNSTABLE_STDOUT, exit_code=1, verified=False)
    result = aggregate(score_records([stable, unstable]))
    assert len(result["run_to_run"]) == 1
    row = result["run_to_run"][0]
    assert row["repeats"] == 2
    assert row["verified_mean"] == 0.5
    assert row["verified_variance"] == 0.25


def test_scoring_is_deterministic_and_side_effect_free():
    record = make_record()
    frozen = copy.deepcopy(record)
    first = score_records([record])
    second = score_records([record])
    assert first == second
    assert record == frozen


def test_scripted_usage_marks_aggregate_estimated():
    result = aggregate(score_records([make_record()]))
    assert result["overall"]["usage_estimated"] is True
