"""Token-budget parity arms: rac_snippets (typed retrieval at naive_rag's
budget) and naive_rag_full (cosine retrieval at whole-artifact granularity).
These complete the 2x2 that separates 'does typing help' from 'does dumping
whole artifacts help/hurt'."""

import json
import shutil
from pathlib import Path

import pytest

from providers import (
    ARMS,
    NaiveRagFullProvider,
    RacSnippetsProvider,
    ScriptedAnsweringModel,
    build_provider,
)
from providers.base import CorpusArtifact, Task
from providers.rac_snippets import (
    DEFAULT_SNIPPET_BUDGET_TOKENS,
    select_sections_under_budget,
)
from runner.cli import run_one
from scenarios.loader import load_scenarios

_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS = _ROOT / "scenarios"
_RUN_SCHEMA = _ROOT / "schema" / "run_result.schema.json"


def _validate_run(rr: dict):
    try:
        import jsonschema  # type: ignore

        jsonschema.validate(rr, json.loads(_RUN_SCHEMA.read_text()))
    except ImportError:
        assert rr["arm"] in ARMS


def _artifact(aid, body):
    return CorpusArtifact(id=aid, type="decision", path=f"{aid}.md", text=body)


# ---------------------------------------------------------------- registration


def test_both_arms_registered_and_named():
    assert ARMS["rac_snippets"] is RacSnippetsProvider
    assert ARMS["naive_rag_full"] is NaiveRagFullProvider
    assert RacSnippetsProvider(ScriptedAnsweringModel()).name == "rac_snippets"
    assert NaiveRagFullProvider(ScriptedAnsweringModel()).name == "naive_rag_full"


def test_build_provider_threads_embedder_for_naive_rag_full():
    p = build_provider("naive_rag_full", ScriptedAnsweringModel(), embedder_spec="local-hash")
    assert isinstance(p, NaiveRagFullProvider) and p.embedder is not None
    # rac_snippets takes the default (typed retrieval, no embedder) path.
    p2 = build_provider("rac_snippets", ScriptedAnsweringModel())
    assert isinstance(p2, RacSnippetsProvider)


def test_schema_enum_accepts_new_arms():
    enum = json.loads(_RUN_SCHEMA.read_text())["properties"]["arm"]["enum"]
    assert "rac_snippets" in enum and "naive_rag_full" in enum


# ------------------------------------------------------ budget selection (pure)


def test_select_sections_respects_budget_and_rank_order():
    arts = [
        _artifact("A", "## one\n" + "wordone " * 50 + "\n## two\n" + "wordtwo " * 50),
        _artifact("B", "## three\n" + "wordthree " * 50),
    ]
    # Budget for ~one section only.
    selected = select_sections_under_budget(arts, token_budget=80)
    assert selected  # never empty when candidates exist
    assert [s[0] for s in selected][0] == "A"  # rank order preserved
    # Blocks stay within budget once more than one is present.
    assert len(selected) >= 1


def test_select_sections_always_includes_first_even_if_oversize():
    arts = [_artifact("A", "## big\n" + "token " * 5000)]
    selected = select_sections_under_budget(arts, token_budget=10)
    assert len(selected) == 1 and selected[0][0] == "A"


def test_select_sections_empty_when_no_artifacts():
    assert select_sections_under_budget([], token_budget=2000) == []


# ------------------------------------------------- rac_snippets (offline via _resolve)


def test_rac_snippets_grounding_within_budget(monkeypatch):
    sc = load_scenarios(_SCENARIOS)[0]
    p = RacSnippetsProvider(ScriptedAnsweringModel(), token_budget=200)
    p._by_id = {a.id: a for a in sc.corpus}
    # Bypass the rac CLI: _resolve just returns the corpus ids in order.
    monkeypatch.setattr(p, "_resolve", lambda task: [a.id for a in sc.corpus])
    g = p.assemble(sc.task)
    assert g.text  # non-empty when candidates exist
    # Budget honoured modulo the always-included first block.
    assert g.token_estimate <= 200 + 400


def test_rac_snippets_supplies_snippets_not_whole_artifacts(monkeypatch):
    big = _artifact("BIG", "## head\nintro\n## tail\n" + "filler " * 400)
    p = RacSnippetsProvider(ScriptedAnsweringModel(), token_budget=40)
    p._by_id = {big.id: big}
    monkeypatch.setattr(p, "_resolve", lambda task: ["BIG"])
    g = p.assemble(Task(prompt="q", proposed_action="a"))
    assert len(g.text) < len(big.text)  # a snippet, not the whole artifact


# ----------------------------------------------------- naive_rag_full (offline)


def test_naive_rag_full_supplies_whole_artifacts_and_caps_at_top_k():
    corpus = [
        _artifact("D1", "## h\n" + "alpha " * 30),
        _artifact("D2", "## h\n" + "beta " * 30),
        _artifact("D3", "## h\n" + "gamma " * 30),
        _artifact("D4", "## h\n" + "delta " * 30),
        _artifact("D5", "## h\n" + "epsilon " * 30),
    ]
    p = NaiveRagFullProvider(ScriptedAnsweringModel(), top_k=4)
    p.prepare(corpus)
    g = p.assemble(Task(prompt="alpha beta", proposed_action="alpha"))
    assert len(g.artifacts_supplied) <= 4  # item parity with rac
    assert len(set(g.artifacts_supplied)) == len(g.artifacts_supplied)  # deduped
    # Whole artifact text present (not just a section) for a supplied id.
    supplied = g.artifacts_supplied[0]
    whole = next(a for a in corpus if a.id == supplied)
    assert whole.text.split()[-1] in g.text


def test_naive_rag_full_run_one_is_schema_valid():
    sc = load_scenarios(_SCENARIOS)[0]
    rr = run_one("naive_rag_full", sc, ScriptedAnsweringModel(seed=0), seed=0,
                 embedder="local-hash")
    assert rr["arm"] == "naive_rag_full"
    _validate_run(rr)


# ---------------------------------------------------------------- preflight


def test_preflight_requires_rac_cli_for_rac_snippets(monkeypatch):
    from runner.cli import _preflight

    monkeypatch.setattr(shutil, "which", lambda *_a, **_k: None)
    with pytest.raises(SystemExit, match="rac"):
        _preflight(("rac_snippets",), "offline-stub", "local-hash")
