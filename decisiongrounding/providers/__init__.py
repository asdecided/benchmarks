"""Benchmark arms and the shared provider-adapter contract.

Every arm implements `prepare(corpus)` / `respond(task) -> ProposedChange` and
feeds a held-constant answering model behind a held-constant scaffold. Arms
differ ONLY in how they assemble grounding.
"""

from __future__ import annotations

from .answering import (
    AnsweringModel,
    ClaudeAnsweringModel,
    GatewayHTTPError,
    OpenAICompatAnsweringModel,
    SchemaMissError,
    ScriptedAnsweringModel,
    error_kind,
)
from .base import (
    Action,
    ContextWindowExceededError,
    CorpusArtifact,
    GroundingContext,
    ProposedChange,
    Provider,
    Task,
)
from .context_dump import ContextDumpProvider
from .embedding import (
    Embedder,
    LiteLLMEmbedder,
    LocalDeterministicEmbedder,
    SentenceTransformerEmbedder,
    VoyageEmbedder,
    make_embedder,
)
from .memory_provider import MemoryProviderArm
from .naive_rag import NaiveRagProvider
from .naive_rag_full import NaiveRagFullProvider
from .no_grounding import NoGroundingProvider
from .rac import RacProvider, resolve_supersedes
from .rac_snippets import RacSnippetsProvider

# Real, runnable arms this pass: context_dump, naive_rag, no_grounding,
# naive_rag_full (offline); rac, rac_snippets (need the external rac CLI).
# naive_rag_full and rac_snippets are the token-budget parity variants that
# complete the 2x2 (retrieval method x grounding granularity).
# memory_provider is a typed stub.
ARMS: dict[str, type[Provider]] = {
    "context_dump": ContextDumpProvider,
    "naive_rag": NaiveRagProvider,
    "naive_rag_full": NaiveRagFullProvider,
    "no_grounding": NoGroundingProvider,
    "rac": RacProvider,
    "rac_snippets": RacSnippetsProvider,
    "memory_provider": MemoryProviderArm,
}

REAL_ARMS = ("context_dump", "naive_rag", "no_grounding")


def make_answering_model(name: str, seed: int) -> AnsweringModel:
    """Build the held-constant answering model from a name.

    `offline-stub` -> ScriptedAnsweringModel (deterministic, no network);
    `claude` -> ClaudeAnsweringModel (pinned Opus 4.8, needs the [real] extra +
    ANTHROPIC_API_KEY); `litellm:<alias>` -> OpenAICompatAnsweringModel (an
    OpenAI-compatible gateway's /chat/completions surface, stdlib transport,
    needs LITELLM_BASE_URL + LITELLM_API_KEY). Lives here so both the CLI and
    the crossover can build backends without importing each other.
    """
    if name == "offline-stub":
        return ScriptedAnsweringModel(seed=seed)
    if name == "claude":
        return ClaudeAnsweringModel(seed=seed)
    if name.startswith("litellm:"):
        return OpenAICompatAnsweringModel(model=name.split(":", 1)[1], seed=seed)
    raise ValueError(
        f"unknown answering model {name!r}; use 'offline-stub', 'claude', or "
        "'litellm:<model-alias>'."
    )


def build_provider(arm: str, answering_model, embedder_spec: str = "local-hash") -> Provider:
    """Instantiate an arm, wiring a real embedder into the embedding-retrieval
    arms when asked. rac_snippets inherits rac (typed retrieval, no embedder)."""
    if arm in ("naive_rag", "naive_rag_full"):
        return ARMS[arm](answering_model, embedder=make_embedder(embedder_spec))
    return ARMS[arm](answering_model)


__all__ = [
    "ARMS",
    "REAL_ARMS",
    "Provider",
    "ContextWindowExceededError",
    "CorpusArtifact",
    "Task",
    "GroundingContext",
    "ProposedChange",
    "Action",
    "AnsweringModel",
    "ScriptedAnsweringModel",
    "ClaudeAnsweringModel",
    "OpenAICompatAnsweringModel",
    "SchemaMissError",
    "GatewayHTTPError",
    "error_kind",
    "make_answering_model",
    "build_provider",
    "Embedder",
    "LocalDeterministicEmbedder",
    "VoyageEmbedder",
    "SentenceTransformerEmbedder",
    "LiteLLMEmbedder",
    "make_embedder",
    "ContextDumpProvider",
    "NaiveRagProvider",
    "NaiveRagFullProvider",
    "NoGroundingProvider",
    "RacProvider",
    "RacSnippetsProvider",
    "resolve_supersedes",
    "MemoryProviderArm",
]
