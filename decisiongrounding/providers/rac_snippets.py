"""`rac_snippets` arm — typed retrieval at naive_rag's grounding budget.

The `rac` arm and `naive_rag` both cap at top_k=4, but that is parity in
ITEMS, not in grounding budget: `rac` supplies up to 4 WHOLE artifacts
(tens of thousands of tokens) while `naive_rag` supplies 4 section snippets
(~1k tokens). Two questions are therefore confounded in a plain rac vs
naive_rag comparison: does typed, supersession-aware retrieval help, and
does dumping whole artifacts help or hurt?

This arm isolates the first. It runs rac's exact typed retrieval
(`RacProvider._resolve` — same candidates, same supersedes traversal, same
top_k), then presents the resolved artifacts as SECTION SNIPPETS under a
token budget matched to naive_rag's typical grounding size — so `rac_snippets`
vs `naive_rag` compares retrieval method at an equal budget, and `rac_snippets`
vs `rac` compares snippet vs whole-artifact granularity at equal retrieval.

Requires the `rac` CLI (inherits `RacProvider`); does not run in the offline
demo. See the 2×2 with `naive_rag_full` (cosine retrieval, whole artifacts).
"""

from __future__ import annotations

from .base import GroundingContext, Task, estimate_tokens
from .grounding_format import format_block, split_sections
from .rac import RacProvider

# naive_rag supplies top_k=4 section snippets; real ADR/PEP/RFC sections run
# ~300-500 tokens, so ~2000 tokens is its typical grounding budget. A fixed
# constant keeps this arm's budget deterministic and independent of which
# other arms are in the run — deriving it from naive_rag's live output would
# couple one arm's grounding to another arm's retrieval (against the
# symmetric-arm rule, CONTRIBUTING #4).
DEFAULT_SNIPPET_BUDGET_TOKENS = 2000


def select_sections_under_budget(artifacts, token_budget):
    """Greedily select `(id, type, section)` triples from `artifacts` (in rank
    order) whose formatted blocks fit within `token_budget`.

    Sections of each artifact are taken in document order. The first section is
    always included even if it alone exceeds the budget, so grounding is never
    empty when candidates exist (an all-or-nothing budget could otherwise
    starve a small budget against a large lead section). Returns the selected
    triples in selection order.
    """
    selected: list[tuple[str, str, str]] = []
    used = 0
    for art in artifacts:
        for section in split_sections(art.text):
            cost = estimate_tokens(format_block(art.id, art.type, section))
            if selected and used + cost > token_budget:
                return selected
            selected.append((art.id, art.type, section))
            used += cost
    return selected


class RacSnippetsProvider(RacProvider):
    name = "rac_snippets"

    def __init__(self, answering_model, top_k: int = 4,
                 token_budget: int = DEFAULT_SNIPPET_BUDGET_TOKENS):
        super().__init__(answering_model, top_k=top_k)
        self.token_budget = token_budget

    def assemble(self, task: Task) -> GroundingContext:
        resolved = [aid for aid in self._resolve(task) if aid in self._by_id]
        artifacts = [self._by_id[aid] for aid in resolved]
        selected = select_sections_under_budget(artifacts, self.token_budget)
        blocks = [format_block(aid, atype, section)
                  for aid, atype, section in selected]
        text = "\n".join(blocks)
        self._grounding = GroundingContext(
            text=text,
            # Artifacts that contributed at least one section.
            artifacts_supplied=tuple(dict.fromkeys(aid for aid, _, _ in selected)),
            token_estimate=estimate_tokens(text),
        )
        return self._grounding
