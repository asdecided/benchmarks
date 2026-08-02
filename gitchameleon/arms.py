# SPDX-License-Identifier: Apache-2.0
"""Grounding arms for the GitChameleon evidence run.

Arms differ ONLY in how they assemble grounding context for the held-constant
answering model (the DG-ADR-0001 single-variable design):

- ``no_grounding`` — the problem alone; the model answers from its weights.
- ``rac``          — the governing version-pin decision retrieved from the
  example's corpus via the live-decision query (`rac find --decisions`),
  driven strictly as an external CLI through the shared harness runner.
- ``naive_rag``    — embedding retrieval over the same corpus. Deliberately a
  seam: the embedder is pinned at funded-run time (mirroring
  decisiongrounding's embedder choice), so the scaffold refuses rather than
  silently shipping a weak stand-in.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from harness.runner import RacRunner

ARMS = ("no_grounding", "rac", "naive_rag")
# How many retrieved decisions the rac arm feeds the answering model.
RAC_TOP_K = 3
NAIVE_RAG_MODEL = "voyage-4-large"
VOYAGE_EMBEDDINGS_URL = "https://api.voyageai.com/v1/embeddings"


class VoyageEmbedder:
    """Pinned, retrieval-only baseline used by the funded naive_rag arm.

    Embeddings are cached by exact text within one run. This matters because
    deterministic distractors recur across per-example corpora; repeated text
    must not create repeated spend or a subtly different baseline.
    """

    model = NAIVE_RAG_MODEL

    def __init__(self, api_key: str | None = None, *, max_attempts: int = 5):
        self.api_key = api_key or os.environ.get("VOYAGE_API_KEY")
        if not self.api_key:
            raise ValueError("the naive_rag arm needs VOYAGE_API_KEY")
        self.max_attempts = max_attempts
        self._cache: dict[tuple[str, str], list[float]] = {}

    def _request(self, texts: list[str], input_type: str) -> list[list[float]]:
        body = json.dumps(
            {
                "input": texts,
                "model": self.model,
                "input_type": input_type,
                "truncation": False,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            VOYAGE_EMBEDDINGS_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
        )
        for attempt in range(self.max_attempts):
            try:
                with urllib.request.urlopen(request, timeout=300) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                vectors = [entry["embedding"] for entry in payload["data"]]
                if len(vectors) != len(texts):
                    raise RuntimeError(
                        f"Voyage returned {len(vectors)} vectors for {len(texts)} texts"
                    )
                return vectors
            except urllib.error.HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt + 1 == self.max_attempts:
                    raise
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2**attempt, 30)
                time.sleep(delay)
            except urllib.error.URLError:
                if attempt + 1 == self.max_attempts:
                    raise
                time.sleep(min(2**attempt, 30))
        raise AssertionError("unreachable")

    def embed(self, texts: list[str], input_type: str) -> list[list[float]]:
        keys = [
            (input_type, hashlib.sha256(text.encode("utf-8")).hexdigest())
            for text in texts
        ]
        missing: list[tuple[tuple[str, str], str]] = [
            (key, text) for key, text in zip(keys, texts) if key not in self._cache
        ]
        if missing:
            vectors = self._request([text for _, text in missing], input_type)
            for (key, _), vector in zip(missing, vectors):
                self._cache[key] = vector
        return [self._cache[key] for key in keys]


def _cosine(left: list[float], right: list[float]) -> float:
    if len(left) != len(right):
        raise ValueError("embedding dimensions differ")
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    return numerator / (left_norm * right_norm) if left_norm and right_norm else 0.0


def rac_grounding(runner: RacRunner, corpus_dir: Path, row: dict) -> list[str]:
    """The rac arm: live-decision retrieval, retrieved artifacts verbatim.

    The query is what an agent grounding itself would ask before writing code
    against a library: which live decisions bind this dependency?
    """
    query = f"{row['library']} version pin"
    returned = runner.find_ids(query, str(corpus_dir), decisions=True)
    grounding: list[str] = []
    for artifact_id in returned[:RAC_TOP_K]:
        resolved = runner.resolve(artifact_id, str(corpus_dir))
        payload = resolved.payload()
        if resolved.exit_code == 0 and "path" in payload:
            grounding.append(Path(payload["path"]).read_text(encoding="utf-8"))
    return grounding


def naive_rag_grounding(
    embedder: VoyageEmbedder, corpus_dir: Path, row: dict
) -> list[str]:
    """Embedding retrieval over the exact corpus presented to RAC.

    Files are ranked by cosine similarity, then path for deterministic ties.
    Query and document input types follow Voyage's retrieval contract.
    """
    paths = sorted(corpus_dir.glob("*.md"))
    documents = [path.read_text(encoding="utf-8") for path in paths]
    if not documents:
        return []
    document_vectors = embedder.embed(documents, "document")
    query_vector = embedder.embed([f"{row['library']} version pin"], "query")[0]
    ranked = sorted(
        zip(paths, documents, document_vectors),
        key=lambda item: (-_cosine(query_vector, item[2]), str(item[0])),
    )
    return [document for _, document, _ in ranked[:RAC_TOP_K]]


def assemble_grounding(
    arm: str,
    runner: RacRunner | None,
    corpus_dir: Path,
    row: dict,
    embedder: VoyageEmbedder | None = None,
) -> list[str]:
    """The grounding context one arm supplies for one example."""
    if arm == "no_grounding":
        return []
    if arm == "rac":
        if runner is None:
            raise ValueError("the rac arm needs a RacRunner (rac CLI on PATH)")
        return rac_grounding(runner, corpus_dir, row)
    if arm == "naive_rag":
        if embedder is None:
            raise ValueError("the naive_rag arm needs the pinned Voyage embedder")
        return naive_rag_grounding(embedder, corpus_dir, row)
    raise ValueError(f"unknown arm {arm!r}; expected one of {ARMS}")


def task_prompt(row: dict) -> str:
    """The held-constant task prompt every arm shares (grounding excluded).

    Deliberately does NOT restate the pinned version: version awareness must
    come from the arm's grounding (or the model's weights), or the comparison
    measures prompt engineering instead of grounding. The upstream problem
    statement itself is preserved verbatim.
    """
    return (
        "Complete the following Python function for this codebase.\n\n"
        f"Problem: {row['problem']}\n\n"
        "Starting code:\n"
        "```python\n"
        f"{row['starting_code']}\n"
        "```\n\n"
        "Return only the completed code."
    )
