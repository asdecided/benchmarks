"""`naive_rag_full` arm — cosine retrieval at whole-artifact granularity.

The complement of `rac_snippets` in the 2×2 (retrieval method × grounding
granularity). It ranks section chunks by cosine similarity exactly like
`naive_rag`, but then expands each top hit to its WHOLE parent artifact and
supplies those (deduped, capped at top_k artifacts for item-parity with
`rac`). So `naive_rag_full` vs `naive_rag` isolates whole-artifact vs snippet
granularity holding the retrieval method constant, and `naive_rag_full` vs
`rac` compares embedding vs typed retrieval at whole-artifact granularity.

Fully offline (inherits `NaiveRagProvider`'s local-hash embedder default).
"""

from __future__ import annotations

from .base import CorpusArtifact, GroundingContext, Task, estimate_tokens
from .embedding import cosine, embed_chunked
from .grounding_format import format_block
from .naive_rag import NaiveRagProvider


class NaiveRagFullProvider(NaiveRagProvider):
    name = "naive_rag_full"

    def __init__(self, answering_model, embedder=None, top_k: int = 4):
        super().__init__(answering_model, embedder=embedder, top_k=top_k)
        self._by_id: dict[str, CorpusArtifact] = {}

    def prepare(self, corpus: list[CorpusArtifact]) -> None:
        # Keep whole artifacts alongside the section chunks the parent embeds,
        # so a top-ranked chunk can be expanded back to its parent.
        self._by_id = {a.id: a for a in corpus}
        super().prepare(corpus)

    def assemble(self, task: Task) -> GroundingContext:
        query = embed_chunked(
            self.embedder, f"{task.prompt}\n{task.proposed_action}", input_type="query"
        )
        ranked = sorted(
            self._chunks, key=lambda c: cosine(query, c.vector), reverse=True
        )
        # Walk chunks best-first, collecting distinct parent artifacts until the
        # top_k budget is met — item parity with rac (whole artifacts, not
        # sections).
        chosen: list[str] = []
        for c in ranked:
            if c.artifact_id not in chosen:
                chosen.append(c.artifact_id)
                if len(chosen) >= self.top_k:
                    break
        blocks = [format_block(aid, self._by_id[aid].type, self._by_id[aid].text)
                  for aid in chosen if aid in self._by_id]
        text = "\n".join(blocks)
        self._grounding = GroundingContext(
            text=text,
            artifacts_supplied=tuple(chosen),
            token_estimate=estimate_tokens(text),
        )
        return self._grounding
