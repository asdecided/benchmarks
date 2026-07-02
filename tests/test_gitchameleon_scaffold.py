# SPDX-License-Identifier: Apache-2.0
"""GitChameleon evidence-run scaffold battery (offline; fixtures only).

Exercises the key-less surface: the corpus builder is deterministic and emits
schema-valid RAC decisions, the dry-run assembles honest prompt bundles (the
rac arm's grounding leads with the governing pin; prompts never leak the
pinned version; grounding never leaks solutions or tests), and the funded-run
seams refuse loudly instead of running weak stand-ins.
"""

from __future__ import annotations

import json
import subprocess
import sys

from conftest import REPO_ROOT

GCB = REPO_ROOT / "gitchameleon"
FIXTURES = GCB / "fixtures" / "sample_problems.json"


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GCB / script), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _build(tmp_path, name: str = "corpus"):
    out = tmp_path / name
    completed = _run(
        "build_corpus.py", "--dataset", str(FIXTURES), "--out", str(out), "--distractors", "2"
    )
    assert completed.returncode == 0, completed.stderr
    return out


def _corpus_bytes(root) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes() for path in sorted(root.rglob("*.md"))
    }


def _fixture_rows() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))["rows"]


def test_corpus_builder_is_deterministic(tmp_path):
    first = _corpus_bytes(_build(tmp_path, "a"))
    second = _corpus_bytes(_build(tmp_path, "b"))
    assert first == second


def test_built_corpora_are_schema_valid(tmp_path):
    corpus = _build(tmp_path)
    completed = subprocess.run(
        ["rac", "validate", str(corpus)], capture_output=True, text=True, check=False
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_decision_artifacts_never_leak_solutions_or_tests(tmp_path):
    corpus = _build(tmp_path)
    leaks = [row["solution"].strip() for row in _fixture_rows()]
    leaks += [row["test"].strip() for row in _fixture_rows()]
    corpus_text = "\n".join(text.decode("utf-8") for text in _corpus_bytes(corpus).values())
    for leak in leaks:
        assert leak not in corpus_text


def _dry_run_bundles(tmp_path, arms: str = "no_grounding,rac") -> list[dict]:
    corpus = _build(tmp_path)
    out = tmp_path / "bundles.jsonl"
    completed = _run(
        "run.py",
        "--dry-run",
        "--dataset",
        str(FIXTURES),
        "--corpus",
        str(corpus),
        "--arms",
        arms,
        "--out",
        str(out),
    )
    assert completed.returncode == 0, completed.stderr
    return [json.loads(line) for line in out.read_text(encoding="utf-8").splitlines()]


def test_rac_arm_grounding_leads_with_the_governing_pin(tmp_path):
    bundles = _dry_run_bundles(tmp_path)
    rac_bundles = [b for b in bundles if b["arm"] == "rac"]
    assert len(rac_bundles) == len(_fixture_rows())
    for bundle in rac_bundles:
        assert bundle["grounding"], bundle["example_id"]
        heading = f"# Library Version Pin: {bundle['library']} {bundle['version']}"
        assert heading in bundle["grounding"][0]


def test_no_grounding_arm_gets_no_grounding(tmp_path):
    bundles = _dry_run_bundles(tmp_path)
    assert all(b["grounding"] == [] for b in bundles if b["arm"] == "no_grounding")


def test_prompt_never_states_the_pinned_version(tmp_path):
    """The honesty rule: version awareness must arrive via grounding, so the
    shared task prompt must not restate the pin (GCB-ADR-0001)."""
    bundles = _dry_run_bundles(tmp_path)
    for bundle in bundles:
        assert bundle["version"] not in bundle["prompt"]


def test_naive_rag_refuses_until_embedder_is_pinned(tmp_path):
    corpus = _build(tmp_path)
    completed = _run(
        "run.py",
        "--dry-run",
        "--dataset",
        str(FIXTURES),
        "--corpus",
        str(corpus),
        "--arms",
        "naive_rag",
        "--out",
        str(tmp_path / "bundles.jsonl"),
    )
    assert completed.returncode == 2
    assert "embedder" in completed.stderr


def test_non_dry_run_refuses_in_the_scaffold(tmp_path):
    completed = _run("run.py", "--dataset", str(FIXTURES))
    assert completed.returncode == 2
    assert "funded-run seam" in completed.stderr
