"""scenarios.overlap: the frequency-weighted lexical-overlap measure and its
banding. Makes 'varied lexical overlap' a measured property."""

from scenarios.loader import load_scenarios
from scenarios.overlap import (
    HIGH_MIN,
    MEDIUM_MIN,
    measured_overlap,
    overlap_band,
    pep_title_doc_freq,
)

_SCENARIOS = "scenarios"


def _by_id():
    return {s.scenario_id: s for s in load_scenarios(_SCENARIOS)}


def test_pep_vocab_loads_offline():
    df, n = pep_title_doc_freq()
    assert n > 100 and df  # the committed provenance has hundreds of PEP titles


def test_band_thresholds_monotonic():
    assert overlap_band(HIGH_MIN) == "high"
    assert overlap_band(MEDIUM_MIN) == "medium"
    assert overlap_band(MEDIUM_MIN - 1e-6) == "low"
    assert overlap_band(0.0) == "low"


def test_prohibition_migration_is_the_high_anchor():
    # The pilot's failure-dominating scenario: Python/language/rewrite vocab
    # saturates PEP titles — the calibration anchor for the "high" band.
    scenarios = _by_id()
    high = measured_overlap(scenarios["prohibition_language_migration"])
    assert overlap_band(high) == "high"
    # ...and it is meaningfully denser than the low-overlap retry scenario.
    low = measured_overlap(scenarios["conflicting_scoped_retry"])
    assert high > low * 3


def test_declared_overlap_matches_measured_for_existing_scenarios():
    # Every scenario that DECLARES a band must measure into that band — the
    # regression guard against task edits silently changing overlap.
    for s in load_scenarios(_SCENARIOS):
        if s.lexical_overlap is not None:
            assert overlap_band(measured_overlap(s)) == s.lexical_overlap, (
                s.scenario_id, measured_overlap(s))
