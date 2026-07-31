# SPDX-License-Identifier: Apache-2.0
"""Deterministic contract and mutation evaluation for AsDecided Sentry."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import statistics
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from harness.errors import UsageError
from harness.gate import evaluate_gate
from harness.scorecard import (
    Scorecard,
    build_metadata,
    render_metrics_json,
    render_scorecard_human,
    render_scorecard_json,
)

BENCHMARK_DIR = Path(__file__).resolve().parent
FINDING_KEYS = ("code", "decision_path", "rule_id", "path", "line")


@dataclass(frozen=True)
class Invocation:
    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    def payload(self) -> dict[str, Any]:
        try:
            value = json.loads(self.stdout)
        except json.JSONDecodeError as exc:
            raise UsageError(f"non-JSON output from {' '.join(self.argv)}: {exc}") from None
        if not isinstance(value, dict):
            raise UsageError(f"non-object output from {' '.join(self.argv)}")
        return value


def _load_json(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        raise UsageError(f"{label} not found: {path}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UsageError(f"cannot read {label}: {path}: {exc}") from None
    if not isinstance(value, dict):
        raise UsageError(f"malformed {label}: expected an object")
    return value


def _load_cases(path: Path) -> list[dict[str, Any]]:
    value = _load_json(path, "case set").get("cases")
    if not isinstance(value, list) or not value:
        raise UsageError(f"malformed case set: {path}: expected a non-empty cases list")
    ids: set[str] = set()
    for index, case in enumerate(value):
        if not isinstance(case, dict):
            raise UsageError(f"malformed case set: case {index} is not an object")
        for required in ("id", "category", "mode", "expected_findings"):
            if required not in case:
                raise UsageError(f"malformed case set: case {index} missing {required}")
        if case["id"] in ids:
            raise UsageError(f"malformed case set: duplicate id {case['id']}")
        if case["mode"] not in ("full", "diff"):
            raise UsageError(f"malformed case set: case {case['id']} has invalid mode")
        if not isinstance(case["expected_findings"], list):
            raise UsageError(f"malformed case set: case {case['id']} findings must be a list")
        ids.add(str(case["id"]))
    return value


def _write_files(root: Path, values: dict[str, str]) -> None:
    for relative, content in values.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")


def _replace_constraint(corpus: Path, case: dict[str, Any]) -> None:
    if "constraint_yaml" not in case and "constraint_section" not in case:
        return
    target = corpus / "enforcement.md"
    text = target.read_text(encoding="utf-8")
    before, remainder = text.split("## Code Constraints\n\n", 1)
    _, after = remainder.split("\n## Category", 1)
    section = case.get("constraint_section")
    if section is None:
        section = f"```yaml\n{case['constraint_yaml']}\n```"
    target.write_text(
        before + "## Code Constraints\n\n" + str(section) + "\n\n## Category" + after,
        encoding="utf-8",
    )


def _git(repo: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise UsageError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def _prepare(case: dict[str, Any], parent: Path) -> tuple[Path, Path, str]:
    corpus = parent / "corpus"
    repository = parent / "repo"
    shutil.copytree(BENCHMARK_DIR / "corpus", corpus)
    shutil.copytree(BENCHMARK_DIR / "repository", repository)
    _replace_constraint(corpus, case)
    _write_files(repository, case.get("base_changes", {}))
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "sentrybench@example.invalid")
    _git(repository, "config", "user.name", "SentryBench")
    _git(repository, "add", ".")
    _git(repository, "commit", "-qm", "fixture base")
    base = _git(repository, "rev-parse", "HEAD")
    _write_files(repository, case.get("changes", {}))
    for relative in case.get("deletes", []):
        target = repository / relative
        if target.exists():
            target.unlink()
    # Git diff does not include untracked additions. Intent-to-add gives new
    # fixture files the same diff visibility they have in a committed PR.
    _git(repository, "add", "-N", ".")
    return corpus, repository, base


def _invoke(
    executable: str,
    cwd: Path,
    mode: str,
    base: str,
    *,
    surface: str = "sentry",
    output: str = "json",
) -> Invocation:
    args = [executable, surface, "corpus"]
    if surface == "gate":
        args.append("--code")
    args.extend(["--repository", "repo"])
    if mode == "full":
        args.append("--full")
    else:
        args.extend(["--base", base])
    args.append("--sarif" if output == "sarif" else "--json")
    completed = subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=False)
    return Invocation(tuple(args), completed.returncode, completed.stdout, completed.stderr)


def _normalise_findings(payload: dict[str, Any]) -> list[dict[str, Any]]:
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise UsageError("Sentry JSON has no findings list")
    return [
        {key: finding.get(key) for key in FINDING_KEYS}
        for finding in findings
        if isinstance(finding, dict)
    ]


def _sentry_gate_projection(payload: dict[str, Any]) -> list[dict[str, Any]]:
    findings = payload.get("findings")
    if not isinstance(findings, list):
        raise UsageError("gate JSON has no findings list")
    projected = []
    for finding in findings:
        if not isinstance(finding, dict) or finding.get("source") != "sentry":
            continue
        projected.append(
            {
                "code": finding.get("code"),
                "path": finding.get("path"),
                "line": finding.get("line"),
            }
        )
    return projected


def _sarif_projection(payload: dict[str, Any]) -> list[dict[str, Any]]:
    try:
        results = payload["runs"][0]["results"]
    except (KeyError, IndexError, TypeError):
        raise UsageError("Sentry SARIF has no runs[0].results") from None
    projected = []
    for result in results:
        location = result["locations"][0]["physicalLocation"]
        projected.append(
            {
                "code": result.get("ruleId"),
                "path": location["artifactLocation"]["uri"],
                "line": location.get("region", {}).get("startLine"),
            }
        )
    return projected


def _run_case(case: dict[str, Any], executable: str) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix=f"sentrybench-{case['id']}-") as raw:
        parent = Path(raw)
        _, _, base = _prepare(case, parent)
        result = _invoke(executable, parent, case["mode"], base)
        payload = result.payload()
        actual = _normalise_findings(payload)
        expected = case["expected_findings"]
        checks = {
            "exit_code": result.exit_code == (1 if expected else 0),
            "ok": payload.get("ok") is (not expected),
            "findings": actual == expected,
        }
        if "expected_coverage" in case:
            coverage = payload.get("coverage", {})
            checks["coverage"] = all(
                coverage.get(key) == value for key, value in case["expected_coverage"].items()
            )

        sarif_ok: bool | None = None
        if case.get("sarif"):
            sarif = _invoke(executable, parent, case["mode"], base, output="sarif")
            sarif_payload = sarif.payload()
            sarif_actual = _sarif_projection(sarif_payload)
            sarif_expected = [
                {"code": item["code"], "path": item["path"], "line": item["line"]}
                for item in expected
            ]
            sarif_ok = sarif.exit_code == (1 if expected else 0) and sarif_actual == sarif_expected
            checks["sarif"] = sarif_ok

        parity_ok: bool | None = None
        if case.get("gate_parity"):
            gate = _invoke(executable, parent, case["mode"], base, surface="gate")
            gate_payload = gate.payload()
            expected_projection = [
                {
                    "code": item["code"],
                    "path": item["path"],
                    "line": item["line"],
                }
                for item in expected
            ]
            coverage = gate_payload.get("code_coverage")
            parity_ok = (
                gate.exit_code == (1 if expected else 0)
                and _sentry_gate_projection(gate_payload) == expected_projection
                and coverage == payload.get("coverage")
            )
            checks["gate_parity"] = parity_ok

        deterministic_ok: bool | None = None
        if case.get("byte_stable"):
            repeated = _invoke(executable, parent, case["mode"], base)
            deterministic_ok = (
                repeated.exit_code == result.exit_code
                and repeated.stdout == result.stdout
                and repeated.stderr == result.stderr
            )
            checks["byte_stable"] = deterministic_ok

        passed = all(checks.values())
        return {
            "id": case["id"],
            "category": case["category"],
            "mode": case["mode"],
            "violation": bool(case.get("violation")),
            "passed": passed,
            "checks": checks,
            "expected_findings": expected,
            "actual_findings": actual,
            "sarif_ok": sarif_ok,
            "gate_parity_ok": parity_ok,
            "byte_stable": deterministic_ok,
        }


def _ratio(numerator: int, denominator: int) -> float:
    return 1.0 if denominator == 0 else numerator / denominator


def _aggregate(results: list[dict[str, Any]]) -> dict[str, Any]:
    violating = [result for result in results if result["violation"]]
    clean = [
        result
        for result in results
        if not result["expected_findings"] and not result["violation"]
    ]
    attributed = [result for result in results if result["expected_findings"]]
    sarif = [result for result in results if result["sarif_ok"] is not None]
    parity = [result for result in results if result["gate_parity_ok"] is not None]
    deterministic = [result for result in results if result["byte_stable"] is not None]
    by_category: dict[str, Any] = {}
    for category in sorted({result["category"] for result in results}):
        selected = [result for result in results if result["category"] == category]
        by_category[category] = {
            "conformance": _ratio(sum(result["passed"] for result in selected), len(selected))
        }
    return {
        "overall": {
            "conformance": _ratio(sum(result["passed"] for result in results), len(results)),
            "cases_passed": sum(result["passed"] for result in results),
            "cases_total": len(results),
            "negative_violations": sum(
                1 for result in clean if result["actual_findings"]
            ),
            "violation_recall": _ratio(
                sum(result["passed"] for result in violating), len(violating)
            ),
            "clean_pass_rate": _ratio(sum(result["passed"] for result in clean), len(clean)),
            "attribution_accuracy": _ratio(
                sum(result["checks"]["findings"] for result in attributed), len(attributed)
            ),
            "sarif_accuracy": _ratio(
                sum(result["sarif_ok"] is True for result in sarif), len(sarif)
            ),
            "gate_parity": _ratio(
                sum(result["gate_parity_ok"] is True for result in parity), len(parity)
            ),
            "byte_determinism": _ratio(
                sum(result["byte_stable"] is True for result in deterministic),
                len(deterministic),
            ),
        },
        "by_category": by_category,
    }


def _version(executable: str) -> str:
    completed = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, check=False
    )
    if completed.returncode != 0:
        raise UsageError(f"{executable} --version failed: {completed.stderr.strip()}")
    return completed.stdout.strip()


def run_scorecard(cases_path: Path, executable: str) -> Scorecard:
    if shutil.which(executable) is None:
        raise UsageError(f"'{executable}' not found on PATH")
    cases = _load_cases(cases_path)
    results = [_run_case(case, executable) for case in cases]
    results.sort(key=lambda result: result["id"])
    metadata = build_metadata(
        rac_version=_version(executable),
        root=str(BENCHMARK_DIR / "corpus"),
        queries_path=str(cases_path),
        n_queries=len(cases),
    )
    metadata["benchmark"] = "sentry"
    return Scorecard(metrics=_aggregate(results), metadata=metadata, per_query=results)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return ordered[index]


def run_performance(executable: str, iterations: int) -> dict[str, Any]:
    if iterations < 1:
        raise UsageError("--iterations must be at least 1")
    cases = {case["id"]: case for case in _load_cases(BENCHMARK_DIR / "cases.json")}
    output: dict[str, Any] = {
        "schema_version": "1",
        "benchmark": "sentry-performance",
        "engine": _version(executable),
        "iterations": iterations,
        "profiles": {},
    }
    for name, case_id in (("full_clean", "C01"), ("diff_violation", "V02")):
        with tempfile.TemporaryDirectory(prefix=f"sentrybench-perf-{name}-") as raw:
            parent = Path(raw)
            _, _, base = _prepare(cases[case_id], parent)
            samples: list[float] = []
            for _ in range(iterations):
                started = time.perf_counter_ns()
                result = _invoke(executable, parent, cases[case_id]["mode"], base)
                samples.append((time.perf_counter_ns() - started) / 1_000_000)
                if result.exit_code not in (0, 1):
                    raise UsageError(f"performance profile {name} failed: {result.stderr}")
            output["profiles"][name] = {
                "median_ms": round(statistics.median(samples), 3),
                "p95_ms": round(_percentile(samples, 0.95), 3),
                "min_ms": round(min(samples), 3),
                "max_ms": round(max(samples), 3),
            }
    return output


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run deterministic SentryBench evaluation.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--update-baseline", action="store_true")
    mode.add_argument("--performance", action="store_true")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--cases", type=Path, default=BENCHMARK_DIR / "cases.json")
    parser.add_argument("--baseline", type=Path, default=BENCHMARK_DIR / "baseline.json")
    parser.add_argument("--config", type=Path, default=BENCHMARK_DIR / "config.json")
    parser.add_argument("--iterations", type=int, default=10)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    executable = os.environ.get("RAC_BIN", "decided")
    try:
        if args.performance:
            print(json.dumps(run_performance(executable, args.iterations), indent=2))
            return 0
        scorecard = run_scorecard(args.cases, executable)
        if args.update_baseline:
            args.baseline.write_text(
                render_metrics_json(scorecard.metrics) + "\n", encoding="utf-8"
            )
            print(f"sentry: baseline updated -> {args.baseline}")
            return 0
        if args.check:
            baseline = _load_json(args.baseline, "baseline")
            config = _load_json(args.config, "config")
            failures = evaluate_gate(scorecard.metrics, baseline, config)
            if failures:
                for failure in failures:
                    print(failure.render())
                return 1
            print("sentry: gate PASS")
            return 0
        print(
            render_scorecard_json(scorecard)
            if args.json
            else render_scorecard_human(scorecard, "conformance")
        )
        return 0
    except UsageError as exc:
        print(f"sentry: {exc}", file=os.sys.stderr)
        return 2
