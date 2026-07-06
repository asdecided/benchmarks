# SPDX-License-Identifier: Apache-2.0
"""The two arms — one variable (granularity), one shared lexical ranking family.

- ``artifacts`` arm: the per-file RAC variant, served warm from ``rac mcp
  --root DIR/artifacts --index`` (ADR-100/101 persistent index; the server
  builds it on first start and answers every case from the one warm process).
  Topic cases go to ``search_artifacts``; supersession and related cases go to
  ``find_decisions``, the typed live-decision tool whose filter the per-file
  ``Superseded`` status enables — so a superseded ancestor is never returned.

- ``canon`` arm: the monolithic variant, chunked by heading and ranked by the
  streaming BM25 in ``bm25`` (same lowercase / non-alnum tokenisation family as
  the engine's search, ADR-037). It has NO liveness or supersession logic — a
  document carries no typed identity for a live filter to read — which is
  exactly the difference the benchmark measures. Decision cases score against
  the decisions canon; a case whose target is a decision never consults the
  requirements canon.

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

from bm25 import rank, tokenize  # noqa: E402

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


def run_canon_arm(corpus: Path, cases: list[dict]) -> dict[str, list[str]]:
    """Chunk the decisions canon and BM25-rank it per case.

    Every case in this member targets a decision, so only the decisions canon
    is consulted; the query tokens come from the case's own query string.
    """
    canon = corpus / "canon" / "decisions-canon.md"
    queries = {case["id"]: tokenize(case["query"]) for case in cases}
    return rank(canon, queries)
