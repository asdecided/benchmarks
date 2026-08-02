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
sys.path.insert(0, str(GCB))
import arms as arms_mod
import fetch_dataset as fetch_mod


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
        "build_corpus.py",
        "--dataset",
        str(FIXTURES),
        "--out",
        str(out),
        "--distractors",
        "2",
    )
    assert completed.returncode == 0, completed.stderr
    return out


def _corpus_bytes(root) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*.md"))
    }


def _fixture_rows() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))["rows"]


def test_funded_run_config_matches_implemented_pins():
    config = json.loads((GCB / "run-config.json").read_text(encoding="utf-8"))
    assert config["status"] == "preregistered-not-run"
    assert config["arms"] == list(arms_mod.ARMS)
    assert config["answering"]["model"] == "claude-opus-4-8"
    assert config["naive_rag"]["model"] == arms_mod.NAIVE_RAG_MODEL
    assert config["naive_rag"]["top_k"] == arms_mod.RAC_TOP_K
    assert len(config["dataset"]["revision"]) == 40
    assert len(config["upstream_harness"]["commit"]) == 40


def test_corpus_builder_is_deterministic(tmp_path):
    first = _corpus_bytes(_build(tmp_path, "a"))
    second = _corpus_bytes(_build(tmp_path, "b"))
    assert first == second


def test_dataset_revision_preserves_the_owner_name_path(monkeypatch):
    seen = []

    def fake_get(url):
        seen.append(url)
        return {"sha": "dataset-pin"}

    monkeypatch.setattr(fetch_mod, "_get_json", fake_get)
    assert fetch_mod.dataset_revision() == "dataset-pin"
    assert seen == ["https://huggingface.co/api/datasets/cabbage972/GitChameleon-2.0"]


def test_dataset_rows_are_fetched_at_the_exact_revision(monkeypatch):
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def read(self):
            return b'{"example_id":"7"}\n'

    def fake_open(url):
        seen.append(url)
        return Response()

    monkeypatch.setattr(fetch_mod.urllib.request, "urlopen", fake_open)
    assert fetch_mod.fetch_rows("abc123") == [{"example_id": "7"}]
    assert seen == [
        (
            "https://huggingface.co/datasets/cabbage972/GitChameleon-2.0/"
            "resolve/abc123/dataset.jsonl"
        )
    ]


def test_built_corpora_are_schema_valid(tmp_path):
    corpus = _build(tmp_path)
    completed = subprocess.run(
        ["decided", "validate", str(corpus)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_decision_artifacts_never_leak_solutions_or_tests(tmp_path):
    corpus = _build(tmp_path)
    leaks = [row["solution"].strip() for row in _fixture_rows()]
    leaks += [row["test"].strip() for row in _fixture_rows()]
    corpus_text = "\n".join(
        text.decode("utf-8") for text in _corpus_bytes(corpus).values()
    )
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


def test_naive_rag_refuses_without_the_pinned_embedder_key(tmp_path, monkeypatch):
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
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
    assert "VOYAGE_API_KEY" in completed.stderr


def test_naive_rag_ranks_the_governing_pin_first(tmp_path):
    corpus = _build(tmp_path)
    row = _fixture_rows()[0]
    corpus_dir = corpus / f"example-{row['example_id']}"

    class FakeEmbedder:
        def embed(self, texts, input_type):
            if input_type == "query":
                return [[1.0, 0.0]]
            heading = f"# Library Version Pin: {row['library']} {row['version']}"
            return [[1.0, 0.0] if heading in text else [0.0, 1.0] for text in texts]

    grounding = arms_mod.naive_rag_grounding(FakeEmbedder(), corpus_dir, row)
    assert len(grounding) == 3
    assert f"# Library Version Pin: {row['library']} {row['version']}" in grounding[0]


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
        "run.py",
        "--dry-run",
        "--dataset",
        str(FIXTURES),
        "--corpus",
        str(corpus),
        "--out",
        str(out),
    )
    assert completed.returncode == 0, completed.stderr
    return str(out)


def _solutions(tmp_path, out_name: str) -> dict[str, list[dict]]:
    completed = _run(
        "run.py",
        "solutions",
        "--bundles",
        _bundles_file(tmp_path),
        "--answering",
        "offline-stub",
        "--out",
        str(tmp_path / out_name),
    )
    assert completed.returncode == 0, completed.stderr
    out: dict[str, list[dict]] = {}
    for path in sorted((tmp_path / out_name).glob("solutions-*.jsonl")):
        arm = path.stem.removeprefix("solutions-")
        out[arm] = [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]
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
            assert len(rec["prompt_sha256"]) == 64
            assert len(rec["grounding_sha256"]) == 64


def test_solutions_resume_only_answers_missing_examples(tmp_path):
    bundles = _bundles_file(tmp_path)
    out = tmp_path / "resume-solutions"
    first = _run(
        "run.py",
        "solutions",
        "--bundles",
        bundles,
        "--answering",
        "offline-stub",
        "--arms",
        "no_grounding",
        "--limit",
        "1",
        "--out",
        str(out),
    )
    assert first.returncode == 0, first.stderr
    second = _run(
        "run.py",
        "solutions",
        "--bundles",
        bundles,
        "--answering",
        "offline-stub",
        "--arms",
        "no_grounding",
        "--limit",
        "2",
        "--resume",
        "--out",
        str(out),
    )
    assert second.returncode == 0, second.stderr
    records = [
        json.loads(line)
        for line in (out / "solutions-no_grounding.jsonl").read_text().splitlines()
    ]
    assert len(records) == 2
    assert len({record["example_id"] for record in records}) == 2


def test_solutions_resume_refuses_a_different_seed(tmp_path):
    bundles = _bundles_file(tmp_path)
    out = tmp_path / "incompatible-resume"
    first = _run(
        "run.py",
        "solutions",
        "--bundles",
        bundles,
        "--answering",
        "offline-stub",
        "--arms",
        "rac",
        "--limit",
        "1",
        "--seed",
        "0",
        "--out",
        str(out),
    )
    assert first.returncode == 0, first.stderr
    second = _run(
        "run.py",
        "solutions",
        "--bundles",
        bundles,
        "--answering",
        "offline-stub",
        "--arms",
        "rac",
        "--limit",
        "1",
        "--seed",
        "1",
        "--resume",
        "--out",
        str(out),
    )
    assert second.returncode == 2
    assert "cannot resume incompatible record" in second.stderr


def test_solutions_refuse_real_backends_without_keys(tmp_path, monkeypatch):
    monkeypatch.delenv(
        "ANTHROPIC_API_KEY", raising=False
    )  # the subprocess inherits os.environ
    completed = _run(
        "run.py",
        "solutions",
        "--bundles",
        _bundles_file(tmp_path),
        "--answering",
        "claude",
        "--out",
        str(tmp_path / "sol"),
    )
    assert completed.returncode != 0
    assert "ANTHROPIC_API_KEY" in (completed.stderr + completed.stdout)


def _score_records(tmp_path) -> list[dict]:
    records = tmp_path / "resolution_records.jsonl"
    completed = _run(
        "run.py",
        "score",
        "--arm",
        "rac",
        "--eval-results",
        str(EVAL_RAC),
        "--out",
        str(records),
        "--answering-model",
        "claude-opus-4-8",
        "--upstream-harness",
        "test-commit",
    )
    assert completed.returncode == 0, completed.stderr
    completed = _run(
        "run.py",
        "score",
        "--arm",
        "no_grounding",
        "--eval-results",
        str(EVAL_NONE),
        "--out",
        str(records),
        "--append",
    )
    assert completed.returncode == 0, completed.stderr
    return [
        json.loads(line) for line in records.read_text(encoding="utf-8").splitlines()
    ]


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


def test_stats_refuses_incomplete_required_arms(tmp_path):
    records = tmp_path / "resolution_records.jsonl"
    _score_records(tmp_path)
    rac_ids = [
        json.loads(line)["example_id"]
        for line in records.read_text(encoding="utf-8").splitlines()
        if json.loads(line)["arm"] == "rac"
    ]
    removed_id = rac_ids[-1]
    kept = [
        line
        for line in records.read_text(encoding="utf-8").splitlines()
        if not (
            json.loads(line)["arm"] == "rac"
            and json.loads(line)["example_id"] == removed_id
        )
    ]
    records.write_text("\n".join(kept) + "\n", encoding="utf-8")
    completed = _run(
        "run.py",
        "stats",
        "--records",
        str(records),
        "--require-arms",
        "no_grounding,rac",
    )
    assert completed.returncode == 2
    assert "incomplete paired records" in completed.stderr
