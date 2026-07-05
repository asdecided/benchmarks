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


def test_bare_invocation_points_at_the_modes(tmp_path):
    completed = _run("run.py", "--dataset", str(FIXTURES))
    assert completed.returncode == 2
    assert "solutions / score / stats" in completed.stderr


# --- the resolution co-primary pipeline (GCB-ADR-0002), offline ---------------

EVAL_RAC = GCB / "fixtures" / "sample_eval_results_rac.csv"
EVAL_NONE = GCB / "fixtures" / "sample_eval_results_no_grounding.csv"


def _bundles_file(tmp_path) -> str:
    corpus = _build(tmp_path)
    out = tmp_path / "bundles.jsonl"
    completed = _run(
        "run.py", "--dry-run", "--dataset", str(FIXTURES), "--corpus", str(corpus),
        "--out", str(out),
    )
    assert completed.returncode == 0, completed.stderr
    return str(out)


def _solutions(tmp_path, out_name: str) -> dict[str, list[dict]]:
    completed = _run(
        "run.py", "solutions", "--bundles", _bundles_file(tmp_path),
        "--answering", "offline-stub", "--out", str(tmp_path / out_name),
    )
    assert completed.returncode == 0, completed.stderr
    out: dict[str, list[dict]] = {}
    for path in sorted((tmp_path / out_name).glob("solutions-*.jsonl")):
        arm = path.stem.removeprefix("solutions-")
        out[arm] = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return out


def test_offline_stub_solutions_are_deterministic_and_upstream_shaped(tmp_path):
    first = _solutions(tmp_path, "sol-a")
    second = _solutions(tmp_path, "sol-b")
    assert first == second
    assert set(first) == {"no_grounding", "rac"}
    for arm, records in first.items():
        assert len(records) == len(_fixture_rows())
        for rec in records:
            # the upstream Solution contract: example_id + answer (extras ignored)
            assert isinstance(rec["example_id"], str) and rec["answer"]
            assert rec["arm"] == arm
            assert "offline-stub" in rec["answer"]  # plumbing output is labelled


def test_solutions_refuse_real_backends_without_keys(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # the subprocess inherits os.environ
    completed = _run(
        "run.py", "solutions", "--bundles", _bundles_file(tmp_path),
        "--answering", "claude", "--out", str(tmp_path / "sol"),
    )
    assert completed.returncode != 0
    assert "ANTHROPIC_API_KEY" in (completed.stderr + completed.stdout)


def _score_records(tmp_path) -> list[dict]:
    records = tmp_path / "resolution_records.jsonl"
    completed = _run(
        "run.py", "score", "--arm", "rac", "--eval-results", str(EVAL_RAC),
        "--out", str(records), "--answering-model", "claude-opus-4-8",
        "--upstream-harness", "test-commit",
    )
    assert completed.returncode == 0, completed.stderr
    completed = _run(
        "run.py", "score", "--arm", "no_grounding", "--eval-results", str(EVAL_NONE),
        "--out", str(records), "--append",
    )
    assert completed.returncode == 0, completed.stderr
    return [json.loads(line) for line in records.read_text(encoding="utf-8").splitlines()]


def test_score_emits_schema_valid_paired_records(tmp_path):
    records = _score_records(tmp_path)
    assert len(records) == 6  # 3 examples x 2 arms
    try:
        import jsonschema  # type: ignore
    except ImportError:
        for rec in records:
            assert {"example_id", "arm", "passed"} <= set(rec)
        return
    schema = json.loads((GCB / "schema" / "resolution_record.schema.json").read_text())
    for rec in records:
        jsonschema.validate(rec, schema)


def test_stats_reproduces_the_hand_computed_mcnemar(tmp_path):
    records = tmp_path / "resolution_records.jsonl"
    _score_records(tmp_path)
    completed = _run("run.py", "stats", "--records", str(records))
    assert completed.returncode == 0, completed.stderr
    stats = json.loads(completed.stdout)
    pair = stats["pairs"]["rac_vs_no_grounding"]
    # fixture design: rac passes 3/3, no_grounding 1/3 -> a=1, b=2, c=0, d=0
    assert pair["table"] == [1, 2, 0, 0]
    # exact two-sided binomial at min(2,0)=0 of 2 discordant: 2 * (1/4) = 0.5
    assert pair["mcnemar"]["p_value"] == 0.5
    assert pair["odds_ratio"]["degenerate"] is True
