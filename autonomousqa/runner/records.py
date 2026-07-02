"""Run records: the benchmark's durable, re-scorable evidence.

A record captures everything a verdict needs — the exact harness config, the
agent's raw stdout and exit code, the metered token usage, and the wall
clock — so scoring can be re-derived offline, deterministically, without
re-running any agent or re-spending any token.

The results directory is append-only: runs stream to a `.partial.jsonl`
sidecar as they land, then the finished report is written once. Existing
files are never mutated.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

from runner import HARNESS_VERSION, RECORD_SCHEMA_VERSION

RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"


def utc_stamp() -> str:
    return time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())


def build_record(*, app, capability, agent_name: str, agent_version: str,
                 invocation_argv: list[str], mode: str, model: str | None,
                 n: int, max_steps: int | None, outcome: dict, usage: dict,
                 wall_clock_s: float, stdout: str, stderr: str,
                 proofread: dict | None = None) -> dict:
    """Assemble one run record. `outcome` is AgentOutcome.as_dict()."""
    return {
        "schema_version": RECORD_SCHEMA_VERSION,
        "harness_version": HARNESS_VERSION,
        "record_id": uuid.uuid4().hex[:12],
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "app": {"name": app.name, "modality": app.modality, "frozen": app.frozen},
        "capability": {
            "id": capability.id,
            "tier": capability.tier,
            "expected": capability.expected,
            "negative": capability.negative,
        },
        "agent": {"name": agent_name, "version": agent_version,
                  "invocation": invocation_argv},
        "config": {"mode": mode, "model": model, "n": n, "max_steps": max_steps},
        "outcome": outcome,
        "usage": usage,
        "timing": {"wall_clock_s": round(wall_clock_s, 3)},
        "raw": {"stdout": stdout, "stderr_tail": stderr[-4000:]},
    }


class ReportWriter:
    """Append-only writer: durable JSONL sidecar, then one final report."""

    def __init__(self, label: str, results_dir: Path = RESULTS_DIR):
        self.label = label
        self.results_dir = results_dir
        self.stamp = utc_stamp()
        self.records: list[dict] = []
        self.partial_path = results_dir / f"run-{self.stamp}-{label}.partial.jsonl"

    def append(self, record: dict) -> None:
        self.records.append(record)
        self.partial_path.parent.mkdir(parents=True, exist_ok=True)
        with self.partial_path.open("a") as sidecar:
            sidecar.write(json.dumps(record) + "\n")

    def finalize(self) -> Path:
        report = {
            "schema_version": RECORD_SCHEMA_VERSION,
            "harness_version": HARNESS_VERSION,
            "label": self.label,
            "created_utc": self.stamp,
            "runs": self.records,
        }
        path = self.results_dir / f"run-{self.stamp}-{self.label}.json"
        if path.exists():  # never mutate: add a short suffix on collision
            path = self.results_dir / f"run-{self.stamp}-{self.label}-{uuid.uuid4().hex[:6]}.json"
        path.write_text(json.dumps(report, indent=2) + "\n")
        self.partial_path.unlink(missing_ok=True)
        return path


def load_reports(paths: list[Path]) -> list[dict]:
    """Load run records from report files (or bare .jsonl sidecars)."""
    records: list[dict] = []
    for path in paths:
        if path.suffix == ".jsonl" or path.name.endswith(".partial.jsonl"):
            records.extend(json.loads(line) for line in path.read_text().splitlines() if line)
        else:
            records.extend(json.loads(path.read_text())["runs"])
    return records
