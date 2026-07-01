# SPDX-License-Identifier: Apache-2.0
"""Shared helpers for the per-tool benchmark battery.

Every test drives a benchmark exactly the way CI does: the subdir's
``run.py`` entry point as a subprocess, with ``rac`` on ``PATH``. Nothing in
this repository imports the engine (DG-ADR-0001).
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
BENCHMARKS = (
    "search-artifacts",
    "find-decisions",
    "get-artifact",
    "get-related",
    "get-summary",
)

_ID_RE = re.compile(r"^id:\s*(\S+)\s*$", re.MULTILINE)


def run_benchmark(bench: str, *args: str) -> subprocess.CompletedProcess:
    """Invoke a benchmark's run.py exactly as CI does."""
    return subprocess.run(
        [sys.executable, str(REPO_ROOT / bench / "run.py"), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def corpus_id(bench: str, filename: str) -> str:
    """The canonical frontmatter id of a fixture corpus file."""
    text = (REPO_ROOT / bench / "corpus" / filename).read_text(encoding="utf-8")
    match = _ID_RE.search(text)
    assert match, f"no id in {bench}/corpus/{filename}"
    return match.group(1)


def load_queries(bench: str) -> dict:
    return json.loads((REPO_ROOT / bench / "queries.json").read_text(encoding="utf-8"))


def write_queries(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def copy_corpus(bench: str, tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    shutil.copytree(REPO_ROOT / bench / "corpus", corpus)
    return corpus


@pytest.fixture(scope="session", autouse=True)
def rac_on_path():
    if shutil.which("rac") is None:
        pytest.fail("rac is not on PATH — the suite consumes rac as an external CLI")


@pytest.fixture(scope="session")
def scorecards() -> dict[str, dict]:
    """One cached --json run per benchmark, shared across the battery."""
    cards: dict[str, dict] = {}
    for bench in BENCHMARKS:
        completed = run_benchmark(bench, "--json")
        assert completed.returncode == 0, completed.stderr
        cards[bench] = json.loads(completed.stdout)
    return cards
