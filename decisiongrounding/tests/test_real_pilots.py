"""Every committed real scenario must be well-formed and genuinely
discriminating: a grounded arm adheres, the ungrounded control does not. This
guards the whole `scenarios_real/` set (the PEP supersession + prohibition
pilots) and any future real scenario against silently degenerate gold labels."""

from pathlib import Path

import pytest

from providers import ScriptedAnsweringModel, build_provider
from scenarios.loader import load_scenarios
from scoring.scorer import score

_ROOT = Path(__file__).resolve().parent.parent
_REAL = _ROOT / "scenarios_real"

_SCENARIOS = load_scenarios(_REAL)
_IDS = [s.scenario_id for s in _SCENARIOS]


def _answer(arm: str, scenario):
    provider = build_provider(arm, ScriptedAnsweringModel(seed=0))
    provider.prepare(list(scenario.corpus))
    return score(scenario, provider.respond(scenario.task))


def test_real_scenarios_present():
    # The pilots we ship; the test fails loudly if a scenario disappears.
    assert {
        "peps_version_supersession",
        "peps_metadata_supersession",
        "peps_annotations_supersession",
        "peps_manylinux_supersession",
        "peps_enum_supersession",
        "peps_timezone_supersession",
        "peps_pattern_matching_supersession",
        "peps_local_version_prohibition",
        "rfc_tls_version_supersession",
        "rfc_rc4_prohibition",
        "rfc_http_semantics_supersession",
        "rfc_date_header_prohibition",
        "rfc_json_supersession",
        "rfc_http_messaging_supersession",
        "rfc_tls_identity_supersession",
        "rfc_json_bom_prohibition",
        "rfc_content_length_te_prohibition",
        "pep8_none_identity_prohibition",
        "w3c_xml_edition_supersession",
    } <= set(_IDS)


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=_IDS)
def test_gold_label_is_consistent(scenario):
    gold = scenario.gold_label
    # Discriminating scenarios name a governing decision that is in the corpus.
    assert gold.governing_decision is not None
    corpus_ids = {a.id for a in scenario.corpus}
    assert gold.governing_decision in corpus_ids
    assert gold.verdict in ("permitted", "prohibited")
    # Pre-registration discipline: the rationale states it was authored blind.
    assert "blind" in gold.rationale.lower()


@pytest.mark.parametrize("scenario", _SCENARIOS, ids=_IDS)
def test_grounded_beats_ungrounded(scenario):
    # context_dump (sees everything) adheres; no_grounding (sees nothing) cannot.
    assert _answer("context_dump", scenario).adherent, "context_dump should adhere"
    assert not _answer("no_grounding", scenario).adherent, "no_grounding should fail"
