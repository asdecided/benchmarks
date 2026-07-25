# SPDX-License-Identifier: Apache-2.0
"""Per-benchmark battery: determinism, gate exit codes, regression injections.

Mirrors rac-core's ``tests/test_eval.py`` proof structure: the serialized
``metrics`` block is byte-identical across runs, ``--check`` exits 0/1/2
correctly, and three regression injections per benchmark each fire a named
rule — (1) the clean fixture passes, (2) deterministically removing a
relevant artifact fires the recall/conformance rule, (3) a forced hard
negative (or, for the pure-contract tools, a forced contract contradiction)
fires the violation/conformance rule. Each injection asserts the exit code
AND the named fired rule.
"""

from __future__ import annotations

import json

import pytest

from conftest import (
    BENCHMARKS,
    copy_corpus,
    corpus_id,
    load_queries,
    run_benchmark,
    write_queries,
)

# One deterministically removed relevant artifact per benchmark, and the rule
# output the removal must fire.
REMOVAL_INJECTIONS = {
    "search-artifacts": ("sab-requirement-offline-viewing.md", "r_at_5"),
    "find-decisions": ("fdb-decision-postgres-ledger.md", "r_at_5"),
    "get-artifact": ("gab-decision-edge-cache.md", "overall.conformance"),
    "get-related": ("grb-roadmap-continuous-delivery.md", "overall.conformance"),
    "get-summary": ("gsb-prompt-meeting-notes.md", "overall.conformance"),
}


# --- Determinism ---------------------------------------------------------------


@pytest.mark.parametrize("bench", BENCHMARKS)
def test_metrics_are_byte_identical_across_runs(bench, scorecards):
    rerun = run_benchmark(bench, "--json")
    assert rerun.returncode == 0, rerun.stderr
    first = json.dumps(scorecards[bench]["metrics"])
    second = json.dumps(json.loads(rerun.stdout)["metrics"])
    assert first == second


@pytest.mark.parametrize("bench", BENCHMARKS)
def test_scorecard_has_exactly_three_top_level_objects(bench, scorecards):
    assert set(scorecards[bench]) == {"metrics", "metadata", "per_query"}


@pytest.mark.parametrize("bench", BENCHMARKS)
def test_metadata_records_version_hashes_and_count(bench, scorecards):
    meta = scorecards[bench]["metadata"]
    assert meta["rac_version"].startswith("decided ")
    assert meta["corpus_hash"].startswith("sha256:")
    assert meta["query_set_hash"].startswith("sha256:")
    assert meta["n_queries"] == len(scorecards[bench]["per_query"])
    assert "generated_at" in meta


@pytest.mark.parametrize("bench", BENCHMARKS)
def test_committed_baseline_matches_a_fresh_run(bench, scorecards):
    from conftest import REPO_ROOT

    committed = json.loads((REPO_ROOT / bench / "baseline.json").read_text(encoding="utf-8"))
    assert committed == scorecards[bench]["metrics"]


# --- Injection 1: the clean fixture passes the gate ------------------------------


@pytest.mark.parametrize("bench", BENCHMARKS)
def test_injection_1_clean_fixture_passes(bench):
    completed = run_benchmark(bench, "--check")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "gate PASS" in completed.stdout


# --- Injection 2: removing a relevant artifact fires the recall rule -------------


@pytest.mark.parametrize("bench", BENCHMARKS)
def test_injection_2_removed_relevant_artifact_fails_the_gate(bench, tmp_path):
    filename, expected_metric = REMOVAL_INJECTIONS[bench]
    corpus = copy_corpus(bench, tmp_path)
    (corpus / filename).unlink()
    completed = run_benchmark(bench, "--check", "--root", str(corpus))
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert expected_metric in completed.stdout
    assert "[floor]" in completed.stdout or "[regression]" in completed.stdout


# --- Injection 3: a forced hard negative fires the violation rule ----------------
# get_artifact and get_summary have no returned-id list to poison, so their
# forced injection is a contract contradiction that must fire the conformance
# floor — the analogue rule for contract-shaped tools (rac-core ADR-097).


def _forced_case(bench: str) -> dict:
    if bench == "search-artifacts":
        return {
            "id": "QFORCE",
            "category": "supersession",
            "query": "polling timer",
            "relevant": [corpus_id(bench, "sab-decision-websocket-updates.md")],
            "must_not_return": [corpus_id(bench, "sab-decision-polling-refresh.md")],
        }
    if bench == "find-decisions":
        # The negative must be LIVE to prove the violation rule is real — a
        # retired decision can never be returned by this tool at all.
        return {
            "id": "QFORCE",
            "category": "live_lookup",
            "query": "billing ledger",
            "relevant": [corpus_id(bench, "fdb-decision-webhook-retries.md")],
            "must_not_return": [corpus_id(bench, "fdb-decision-postgres-ledger.md")],
        }
    if bench == "get-artifact":
        return {
            "id": "CFORCE",
            "category": "not_found",
            "lookup": corpus_id(bench, "gab-decision-edge-cache.md"),
            "expect": {"outcome": "not-found", "exit_code": 1},
        }
    if bench == "get-related":
        queries = load_queries(bench)
        hub = next(c for c in queries["cases"] if c["id"] == "G01")
        forced = dict(hub)
        forced["id"] = "GFORCE"
        forced["must_not_return"] = list(hub["expected_outgoing"])
        return forced
    return {
        "id": "SFORCE",
        "category": "counts",
        "check": "counts",
        "expect": {"total": 999},
    }


EXPECTED_FORCED_RULE = {
    "search-artifacts": "[negative_violations]",
    "find-decisions": "[negative_violations]",
    "get-artifact": "[floor] overall.conformance",
    "get-related": "[negative_violations]",
    "get-summary": "[floor] overall.conformance",
}


@pytest.mark.parametrize("bench", BENCHMARKS)
def test_injection_3_forced_negative_fails_the_gate(bench, tmp_path):
    queries = load_queries(bench)
    queries["cases"].append(_forced_case(bench))
    forced = write_queries(tmp_path / "forced.json", queries)
    completed = run_benchmark(bench, "--check", "--queries", str(forced))
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert EXPECTED_FORCED_RULE[bench] in completed.stdout


# --- Gate exit codes: usage errors are 2, never 0 or 1 ---------------------------


def test_check_missing_baseline_is_usage_error(tmp_path):
    completed = run_benchmark(
        "get-summary", "--check", "--baseline", str(tmp_path / "missing.json")
    )
    assert completed.returncode == 2
    assert "baseline" in completed.stderr


def test_check_unreadable_corpus_is_usage_error(tmp_path):
    completed = run_benchmark(
        "search-artifacts", "--check", "--root", str(tmp_path / "no-such-corpus")
    )
    assert completed.returncode == 2
    assert "corpus" in completed.stderr


def test_check_malformed_query_set_is_usage_error(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text('{"cases": [{"id": "X"}]}', encoding="utf-8")
    completed = run_benchmark("find-decisions", "--check", "--queries", str(bad))
    assert completed.returncode == 2
    assert "malformed query set" in completed.stderr


# --- Re-baselining is human-gated ------------------------------------------------


def test_update_baseline_writes_the_metrics_object(tmp_path, scorecards):
    out_baseline = tmp_path / "baseline.json"
    completed = run_benchmark("get-summary", "--update-baseline", "--baseline", str(out_baseline))
    assert completed.returncode == 0
    written = json.loads(out_baseline.read_text(encoding="utf-8"))
    assert written == scorecards["get-summary"]["metrics"]
