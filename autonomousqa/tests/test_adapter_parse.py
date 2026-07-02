"""The reference adapter's evidence parser: strict, pure, deterministic."""
from agents.proofkeeper import ProofkeeperAdapter

ADAPTER = ProofkeeperAdapter()

STABLE = """Capability: LEDGER-0000000000R1 — Health Endpoint Reports Service Status
Drive: 2 step(s), finished
Compiled: generated/ledger-0000000000r1.spec.ts
Fidelity: 3/3 re-runs green — stable
Write-back: not requested (pass --propose to open a PR)
"""

UNSTABLE = """Capability: X — Y
Drive: 4 step(s), finished
Compiled: generated/x.spec.ts
Fidelity: 1/3 re-runs green — unstable, quarantined
"""


def test_stable_run_parses_verified():
    outcome = ADAPTER.parse(STABLE, 0)
    assert outcome.verified
    assert (outcome.fidelity_passed, outcome.fidelity_attempts) == (3, 3)
    assert outcome.fidelity_stable and outcome.drive_finished
    assert outcome.drive_steps == 2
    assert outcome.spec_path == "generated/ledger-0000000000r1.spec.ts"


def test_unstable_run_is_unverified():
    outcome = ADAPTER.parse(UNSTABLE, 1)
    assert not outcome.verified
    assert outcome.fidelity_stable is False
    assert (outcome.fidelity_passed, outcome.fidelity_attempts) == (1, 3)


def test_exit_zero_without_fidelity_evidence_is_never_verified():
    # A silently no-oping CLI (or truncated output) must not count as verified.
    outcome = ADAPTER.parse("", 0)
    assert not outcome.verified
    assert outcome.error is not None


def test_usage_error_exit_two_is_unverified():
    outcome = ADAPTER.parse("fatal: usage", 2)
    assert not outcome.verified and outcome.error is None


def test_step_budget_stop_parses_unfinished():
    stdout = "Drive: 12 step(s), stopped at step budget\nFidelity: 0/3 re-runs green — unstable, quarantined\n"
    outcome = ADAPTER.parse(stdout, 1)
    assert outcome.drive_finished is False and not outcome.verified


def test_parse_is_deterministic():
    assert ADAPTER.parse(STABLE, 0) == ADAPTER.parse(STABLE, 0)
