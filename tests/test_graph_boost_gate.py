# SPDX-License-Identifier: Apache-2.0
"""Black-box proof for Core's lexical floor on relationship-graph boost."""

from __future__ import annotations

from conftest import REPO_ROOT
from harness.runner import RacRunner

CORPUS = str(REPO_ROOT / "search-artifacts" / "corpus")
QUERIES = ("archive", "retention", "lifecycle", "expiry")
LEXICAL_POLICY = "SAB-6A7E1EC1CA11"
GRAPH_HUB = "SAB-GATEGRAPHH01"


def _find_explained(query: str) -> dict:
    result = RacRunner().run(
        "find", query, CORPUS, "--json", "--explain", "--no-cache"
    )
    assert result.exit_code == 0, result.stderr
    return result.payload()


def _ungated_score(match: dict) -> float:
    """ADR-078's pre-floor formula, used only as counterfactual evidence."""
    components = match["evidence"]["components"]
    return (
        1.0 / (60 + components["lexical_rank"])
        + 0.5 / (60 + components["graph_rank"])
    )


def test_graph_hub_counterfactual_is_real_and_floor_keeps_lexical_policy_first():
    for query in QUERIES:
        payload = _find_explained(query)
        assert payload["matches"][0]["id"] == LEXICAL_POLICY
        by_id = {match["id"]: match for match in payload["matches"]}
        lexical = by_id[LEXICAL_POLICY]
        hub = by_id[GRAPH_HUB]

        # Without the floor, at least one more-connected but weaker candidate
        # beats the policy. This confirms the fixture exercises the regression
        # rather than a no-op (the primary hub is the winner in three cases;
        # a connected catalogue wins the fourth).
        assert max(
            _ungated_score(match)
            for match in payload["matches"]
            if match["id"] != LEXICAL_POLICY
        ) > _ungated_score(lexical)

        lexical_components = lexical["evidence"]["components"]
        hub_components = hub["evidence"]["components"]
        assert lexical_components["graph_floor_ratio"] == 0.85
        assert hub_components["graph_floor_ratio"] == 0.85
        assert lexical_components["graph_gate"] == "applied"
        assert hub_components["graph_gate"] == "clamped"
        assert (
            hub_components["bm25"]
            < lexical_components["bm25"] * hub_components["graph_floor_ratio"]
        )


def test_explain_mode_is_deterministic_and_does_not_change_membership():
    for query in QUERIES:
        first = _find_explained(query)
        second = _find_explained(query)
        assert first == second

        plain = RacRunner().run("find", query, CORPUS, "--json", "--no-cache")
        assert plain.exit_code == 0, plain.stderr
        plain_ids = [match["id"] for match in plain.payload()["matches"]]
        explained_ids = [match["id"] for match in first["matches"]]
        assert explained_ids == plain_ids


def test_ratio_sweep_selects_eighty_five_percent_as_first_passing_grid_point():
    import importlib.util

    path = REPO_ROOT / "search-artifacts" / "ratio_sweep.py"
    spec = importlib.util.spec_from_file_location("ratio_sweep", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    report = module.sweep()
    assert report["minimum_passing_ratio"] == 0.85
    by_ratio = {row["ratio"]: row["p_at_1"] for row in report["results"]}
    assert by_ratio[0.75] < 1.0
    assert by_ratio[0.80] < 1.0
    assert by_ratio[0.85] == 1.0
    assert by_ratio[0.90] == 1.0
    assert by_ratio[0.95] == 1.0
