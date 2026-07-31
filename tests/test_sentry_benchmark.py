# SPDX-License-Identifier: Apache-2.0
"""SentryBench proof: perfect baseline, determinism, regression and usage gates."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from conftest import REPO_ROOT

SENTRY = REPO_ROOT / "sentry"


def run_sentry(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SENTRY / "run.py"), *args],
        capture_output=True,
        text=True,
        check=False,
        env=os.environ.copy(),
    )


def scorecard() -> dict:
    completed = run_sentry("--json")
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout)


def test_sentry_scorecard_is_perfect():
    card = scorecard()
    overall = card["metrics"]["overall"]
    assert overall["cases_total"] == 80
    assert overall["cases_passed"] == 80
    for metric in (
        "conformance",
        "violation_recall",
        "clean_pass_rate",
        "attribution_accuracy",
        "sarif_accuracy",
        "gate_parity",
        "byte_determinism",
    ):
        assert overall[metric] == 1.0
    assert overall["negative_violations"] == 0


def test_sentry_metrics_are_byte_identical():
    first = json.dumps(scorecard()["metrics"])
    second = json.dumps(scorecard()["metrics"])
    assert first == second


def test_sentry_baseline_matches_fresh_run():
    baseline = json.loads((SENTRY / "baseline.json").read_text(encoding="utf-8"))
    assert baseline == scorecard()["metrics"]


def test_sentry_gate_passes():
    completed = run_sentry("--check")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "sentry: gate PASS" in completed.stdout


def test_sentry_contradiction_fails_named_floor(tmp_path):
    cases = json.loads((SENTRY / "cases.json").read_text(encoding="utf-8"))
    case = next(item for item in cases["cases"] if item["id"] == "V01")
    case["expected_findings"][0]["line"] = 999
    path = tmp_path / "contradicted.json"
    path.write_text(json.dumps(cases), encoding="utf-8")
    completed = run_sentry("--check", "--cases", str(path))
    assert completed.returncode == 1
    assert "[floor] overall.conformance" in completed.stdout


def test_sentry_malformed_case_set_is_usage_error(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text('{"cases": [{"id": "bad"}]}', encoding="utf-8")
    completed = run_sentry("--cases", str(path))
    assert completed.returncode == 2
    assert "malformed case set" in completed.stderr


def test_sentry_performance_is_diagnostic_only():
    completed = run_sentry("--performance", "--iterations", "2")
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert "metrics" not in report
    assert set(report["profiles"]) == {"full_clean", "diff_violation"}
    for profile in report["profiles"].values():
        assert profile["median_ms"] > 0
        assert profile["p95_ms"] > 0


def test_sentry_scale_profile_preserves_contract():
    completed = run_sentry("--scale", "--corpus-size", "25")
    assert completed.returncode == 0, completed.stderr
    report = json.loads(completed.stdout)
    assert report["benchmark"] == "sentry-scale"
    assert report["corpus_size"] == 25
    assert report["passed"] is True
    assert all(report["checks"].values())
    assert set(report["profiles"]) == {
        "clean_full",
        "violation_full",
        "violation_diff",
        "gate_diff",
    }


def test_sentry_scale_rejects_too_small_corpus():
    completed = run_sentry("--scale", "--corpus-size", "2")
    assert completed.returncode == 2
    assert "--corpus-size must be at least 3" in completed.stderr
