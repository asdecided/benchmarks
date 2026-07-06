# SPDX-License-Identifier: Apache-2.0
"""The four arms — one variable (granularity), one shared lexical ranking family.

Every arm below the engine shares ONE ranker (``bm25.rank_chunks``); only the
chunk source varies, so a delta between them is a granularity or liveness
effect, never a ranker A/B:

- ``artifacts`` arm: the per-file RAC variant, served warm from ``rac mcp
  --root DIR/artifacts --index`` (ADR-100/101 persistent index; the server
  builds it on first start and answers every case from the one warm process).
  Topic cases go to ``search_artifacts``; supersession and related cases go to
  ``find_decisions``, the typed live-decision tool whose filter the per-file
  ``Superseded`` status enables — so a superseded ancestor is never returned.
  This is the only arm that is the real typed engine (BM25F field weights, graph
  signal, prefix matching, RRF, liveness filter).

- ``bm25-artifacts`` arm (NEW): the SAME per-file decision artifacts, but ranked
  by the member's own streaming Okapi BM25 instead of the engine. Pairing it
  against ``canon`` isolates pure granularity (identical ranker, decision
  content, one file per artifact vs one ``##`` block per artifact); pairing the
  engine ``artifacts`` arm against it isolates what the typed engine adds on top
  of granularity.

- ``canon`` arm: the monolithic variant, chunked by heading and ranked by the
  streaming BM25 in ``bm25`` (same lowercase / non-alnum tokenisation family as
  the engine's search, ADR-037). It has NO liveness or supersession logic — a
  document carries no typed identity for a live filter to read — which is
  exactly the difference the benchmark measures. Decision cases score against
  the decisions canon; a case whose target is a decision never consults the
  requirements canon.

- ``canon-status`` arm (NEW): the canon arm plus one deterministic step — it
  drops any block whose rendered ``### Status`` reads ``Superseded`` before
  ranking. The canon already carries that status line verbatim, so this is the
  strongest honest treatment a monolithic document supports; pairing it against
  ``canon`` measures what a status-aware parser recovers without any typed
  identity.

The engine is consumed strictly as an external server on PATH (DG-ADR-0001);
this module imports the scale member's ``McpClient`` (engine-free stdlib MCP
stdio client) rather than re-implementing it.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scale"))

from measure import McpClient  # noqa: E402  (engine-free MCP stdio client)

from bm25 import (  # noqa: E402
    iter_artifact_chunks,
    iter_live_chunks,
    rank,
    rank_chunks,
    tokenize,
)

# Which MCP tool answers each query class in the artifacts arm.
_TOOL_BY_CLASS = {
    "topic": "search_artifacts",
    "supersession": "find_decisions",
    "related": "find_decisions",
}
# search_artifacts takes 'query'; find_decisions takes 'topic'.
_ARG_BY_TOOL = {"search_artifacts": "query", "find_decisions": "topic"}


def _match_ids(response: dict) -> list[str]:
    """Ranked ids from an MCP tool response, production order preserved."""
    payload = json.loads(response["result"]["content"][0]["text"])
    return [str(m["id"]) for m in payload.get("matches", [])]


def run_artifacts_arm(corpus: Path, cases: list[dict]) -> dict[str, list[str]]:
    """Warm one ``rac mcp --index`` server; return ``{case id: [ranked ids]}``."""
    client = McpClient(str(corpus / "artifacts"), cache=False, index=True)
    returned: dict[str, list[str]] = {}
    try:
        client.initialize()
        for case in cases:
            tool = _TOOL_BY_CLASS[case["class"]]
            arg = _ARG_BY_TOOL[tool]
            response = client.call(tool, {arg: case["query"]})
            returned[case["id"]] = _match_ids(response)
    finally:
        client.close()
    return returned


def run_bm25_artifacts_arm(corpus: Path, cases: list[dict]) -> dict[str, list[str]]:
    """BM25-rank the per-file DECISION artifacts with the member's own ranker.

    The decisions-only domain and the member's Okapi BM25 match the canon arm
    exactly; only granularity differs (one file per artifact vs one ``##`` block
    per artifact), so ``bm25-artifacts`` vs ``canon`` is a pure granularity test.
    """
    artifacts = corpus / "artifacts"
    queries = {case["id"]: tokenize(case["query"]) for case in cases}
    return rank_chunks(
        lambda: iter_artifact_chunks(artifacts, only_type="decision"), queries
    )


def run_canon_arm(corpus: Path, cases: list[dict]) -> dict[str, list[str]]:
    """Chunk the decisions canon and BM25-rank it per case.

    Every case in this member targets a decision, so only the decisions canon
    is consulted; the query tokens come from the case's own query string.
    """
    canon = corpus / "canon" / "decisions-canon.md"
    queries = {case["id"]: tokenize(case["query"]) for case in cases}
    return rank(canon, queries)


def run_canon_status_arm(corpus: Path, cases: list[dict]) -> dict[str, list[str]]:
    """The canon arm, but superseded blocks are dropped before ranking.

    Identical chunking and ranker to ``canon``; the only difference is the
    deterministic status filter, so ``canon-status`` vs ``canon`` measures what
    reading the already-rendered status line recovers.
    """
    canon = corpus / "canon" / "decisions-canon.md"
    queries = {case["id"]: tokenize(case["query"]) for case in cases}
    return rank_chunks(lambda: iter_live_chunks(canon), queries)
