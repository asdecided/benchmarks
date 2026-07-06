"""Embedding backends for the retrieval arms.

The default `LocalDeterministicEmbedder` is a real but dependency-free
bag-of-words hashing embedder: it produces a fixed-width, L2-normalised vector
with no network and no model download, so the spine runs offline and
reproducibly. It is a faithful stand-in for "commodity RAG" — exactly the
threatening baseline the benchmark needs — and its recall genuinely degrades as
the corpus grows past top-k.

For real benchmark runs, swap in a pinned hosted/local embedding model via the
`[real]` extra (see TODO below). Arms depend only on the `Embedder` interface.
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from abc import ABC, abstractmethod

from .base import estimate_tokens

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


class Embedder(ABC):
    """Maps text to a fixed-width vector. Implementations must be deterministic.

    `input_type` is an optional retrieval role (`"query"` or `"document"`).
    Backends that distinguish the two (e.g. Voyage) embed them asymmetrically
    for better retrieval; backends that do not simply ignore it.
    """

    name: str = "base"
    dim: int = 0
    # The backend's max input length in tokens, or None when there is no limit
    # to enforce (e.g. the offline hashing embedder). `embed_chunked` uses this
    # to decide whether a document needs sub-chunking before it is embedded.
    max_input_tokens: int | None = None

    @abstractmethod
    def embed(self, text: str, input_type: str | None = None) -> list[float]:
        ...


class LocalDeterministicEmbedder(Embedder):
    """Hashing bag-of-words embedder. Offline, deterministic, dependency-free."""

    def __init__(self, dim: int = 256) -> None:
        self.dim = dim
        self.name = f"local-hash-bow-{dim}"

    def embed(self, text: str, input_type: str | None = None) -> list[float]:
        # Offline bag-of-words has no notion of query vs document; ignore the role.
        vec = [0.0] * self.dim
        for tok in _tokenize(text):
            h = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
            idx = int.from_bytes(h, "big") % self.dim
            # Signed contribution keeps the space from collapsing to one orthant.
            sign = 1.0 if h[0] & 1 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(v * v for v in vec))
        if norm == 0.0:
            return vec
        return [v / norm for v in vec]


def cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity of two equal-length vectors (assumed roughly unit norm)."""
    return sum(x * y for x, y in zip(a, b))


def _l2_normalize(vec: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vec))
    return vec if norm == 0.0 else [v / norm for v in vec]


def chunk_by_tokens(text: str, max_tokens: int) -> list[str]:
    """Split `text` into pieces that each fit within `max_tokens` (by the same
    ~4-chars/token estimate used elsewhere), breaking on paragraph, then
    sentence, then whitespace boundaries so a chunk never severs a word.

    Used to sub-chunk a document that is too long for an embedder's input
    limit — see `embed_chunked`, which averages the sub-chunk vectors rather
    than truncating the text and discarding whatever fell past the limit.
    """
    max_chars = max(1, max_tokens) * 4
    if len(text) <= max_chars:
        return [text] if text else []

    def _split(units: list[str], sep: str) -> list[str]:
        chunks: list[str] = []
        current = ""
        for unit in units:
            piece = unit if not current else sep + unit
            if current and len(current) + len(piece) > max_chars:
                chunks.append(current)
                current = unit
            else:
                current += piece
        if current:
            chunks.append(current)
        return chunks

    paragraphs = [p for p in text.split("\n\n") if p]
    chunks = _split(paragraphs, "\n\n")
    # A single paragraph can still exceed max_chars (e.g. one long RFC section
    # with no blank lines) — recursively split those on sentence, then
    # whitespace, boundaries until every piece fits.
    out: list[str] = []
    for chunk in chunks:
        if len(chunk) <= max_chars:
            out.append(chunk)
            continue
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", chunk) if s]
        for sub in _split(sentences, " "):
            if len(sub) <= max_chars:
                out.append(sub)
            else:
                words = sub.split()
                for piece in _split(words, " "):
                    if len(piece) <= max_chars:
                        out.append(piece)
                    else:
                        # A single whitespace-free "word" (a URL, hash, or
                        # base64 blob) longer than max_chars on its own — no
                        # boundary left to split on, so hard-slice by
                        # character count as the last resort. Rare, but
                        # without this an oversized token would slip through
                        # over the embedder's own limit, exactly the failure
                        # chunk-and-average exists to avoid.
                        out.extend(
                            piece[i : i + max_chars] for i in range(0, len(piece), max_chars)
                        )
    return out


def embed_chunked(embedder: Embedder, text: str, input_type: str | None = None) -> list[float]:
    """Embed `text`, sub-chunking and mean-pooling when it exceeds the
    embedder's `max_input_tokens` instead of truncating it.

    Truncation silently discards whatever text falls past the limit — for a
    long RFC/ADR section, that is exactly where a supersession or prohibition
    clause is likely to live. Chunk-and-average keeps every part of the
    document represented in the resulting vector (weighted by chunk length),
    at the cost of one extra embedding call per sub-chunk. Short text (the
    common case, and every offline/hash-embedder call) takes the single-call
    path unchanged.
    """
    limit = embedder.max_input_tokens
    if limit is None or estimate_tokens(text) <= limit:
        return embedder.embed(text, input_type=input_type)

    pieces = chunk_by_tokens(text, limit)
    if len(pieces) <= 1:
        return embedder.embed(text, input_type=input_type)

    weight = 0.0
    acc: list[float] | None = None
    for piece in pieces:
        vec = embedder.embed(piece, input_type=input_type)
        w = float(estimate_tokens(piece))
        if acc is None:
            acc = [v * w for v in vec]
        else:
            for i, v in enumerate(vec):
                acc[i] += v * w
        weight += w
    if acc is None or weight == 0.0:
        return embedder.embed(text, input_type=input_type)
    return _l2_normalize([v / weight for v in acc])


class VoyageEmbedder(Embedder):
    """Pinned Voyage AI embeddings (Anthropic's recommended embedding provider).

    Real, reproducible retrieval for benchmark runs. Pin the model id; results
    are deterministic for a fixed model + input. Requires the `[real]` extra
    (`voyageai`) and a VOYAGE_API_KEY. Lazily imported so the offline spine
    keeps importing without the dependency.
    """

    # Voyage's documented context length for the current model family
    # (voyage-3/voyage-4 large + lite): 32,000 tokens. Conservative on purpose —
    # `embed_chunked` sub-chunks and averages rather than truncating, so erring
    # low costs an extra embedding call, not lost content.
    max_input_tokens = 32_000

    def __init__(self, model: str = "voyage-4-large") -> None:
        self.model = model
        self.name = f"voyage:{model}"
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                import voyageai  # type: ignore  # provided by the [real] extra
            except ImportError as exc:
                raise RuntimeError(
                    "the voyage embedder needs the `voyageai` package: "
                    "pip install -e '.[real]'"
                ) from exc
            if not os.environ.get("VOYAGE_API_KEY"):
                raise RuntimeError(
                    "the voyage embedder needs VOYAGE_API_KEY set in the "
                    "environment (export VOYAGE_API_KEY=...)."
                )
            self._client = voyageai.Client()
            # Probe dimensionality once so cosine() comparisons are well-defined.
            probe = self._client.embed(
                ["."], model=self.model, input_type="document"
            ).embeddings[0]
            self.dim = len(probe)
        return self._client

    def embed(self, text: str, input_type: str | None = None) -> list[float]:
        client = self._ensure_client()
        # Voyage embeds queries and documents asymmetrically when told the role.
        vec = client.embed(
            [text], model=self.model, input_type=input_type
        ).embeddings[0]
        return _l2_normalize(list(vec))


class SentenceTransformerEmbedder(Embedder):
    """Pinned local sentence-transformers model. Offline-capable once downloaded.

    A reproducible alternative to a hosted embedder. Requires the
    `[local-embeddings]` extra (`sentence-transformers`). Lazily imported.
    """

    # Pinned models' documented max sequence length (tokens); a conservative
    # fallback covers any other model passed via `st:<model>`.
    _MAX_TOKENS = {"all-MiniLM-L6-v2": 256}
    _DEFAULT_MAX_TOKENS = 256

    def __init__(self, model: str = "all-MiniLM-L6-v2") -> None:
        self.model = model
        self.name = f"st:{model}"
        self._model = None
        self.max_input_tokens = self._MAX_TOKENS.get(model, self._DEFAULT_MAX_TOKENS)

    def _ensure_model(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # type: ignore

            self._model = SentenceTransformer(self.model)
            self.dim = self._model.get_sentence_embedding_dimension()
        return self._model

    def embed(self, text: str, input_type: str | None = None) -> list[float]:
        # This model does not take a query/document role; ignore input_type.
        model = self._ensure_model()
        vec = model.encode(text, normalize_embeddings=True)
        return [float(x) for x in vec]


class LiteLLMEmbedder(Embedder):
    """Embeddings via an OpenAI-compatible gateway's `/embeddings` surface
    (e.g. LiteLLM), so `naive_rag` can run behind any corporate LiteLLM proxy
    with zero HuggingFace/Voyage dependency — e.g. `text-embedding-3-large`
    routed through the same gateway as the `litellm:<alias>` answering
    backend. Transport is stdlib `urllib`; no extra dependency. Configuration
    mirrors the answering backend: base URL from `LITELLM_BASE_URL` (fallback
    `OPENAI_BASE_URL`), key from `LITELLM_API_KEY` (fallback `OPENAI_API_KEY`).
    """

    # text-embedding-3-large's documented input limit (tokens); the honest
    # default for an unspecified gateway alias — override via `max_input_tokens`
    # for a different model.
    _DEFAULT_MAX_TOKENS = 8191

    def __init__(
        self,
        model: str = "text-embedding-3-large",
        timeout: float = 60.0,
        max_input_tokens: int | None = _DEFAULT_MAX_TOKENS,
    ) -> None:
        self.model = model
        self.name = f"litellm:{model}"
        self.timeout = timeout
        self.dim = 0  # probed from the first response (OpenAI-shape has no role)
        self.max_input_tokens = max_input_tokens

    @staticmethod
    def _base_url() -> str:
        base = os.environ.get("LITELLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
        if not base:
            raise RuntimeError(
                "the litellm embedder needs LITELLM_BASE_URL (or OPENAI_BASE_URL) "
                "pointing at the gateway's OpenAI-compatible root."
            )
        return base.rstrip("/")

    @staticmethod
    def _api_key() -> str:
        key = os.environ.get("LITELLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "the litellm embedder needs LITELLM_API_KEY (or OPENAI_API_KEY) "
                "set to the gateway's virtual key."
            )
        return key

    def embed(self, text: str, input_type: str | None = None) -> list[float]:
        # The OpenAI /embeddings surface has no query/document role; ignore it,
        # same as the other role-blind backends.
        import json
        import urllib.error
        import urllib.request

        body = json.dumps({"model": self.model, "input": text}).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url()}/embeddings",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key()}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(
                f"litellm embeddings gateway returned HTTP {exc.code}: {detail}"
            ) from None
        data = payload.get("data") or []
        if not data:
            raise RuntimeError(f"litellm embeddings gateway returned no data: {payload!r}")
        vector = data[0].get("embedding")
        if not vector:
            raise RuntimeError(
                f"litellm embeddings gateway returned no embedding vector: {payload!r}"
            )
        self.dim = len(vector)
        return _l2_normalize([float(x) for x in vector])


def make_embedder(spec: str) -> Embedder:
    """Build an embedder from a spec string.

    `local-hash` (offline default) | `voyage[:model]` | `st[:model]` |
    `litellm[:model]` (an OpenAI-compatible gateway's `/embeddings`, e.g.
    `litellm:text-embedding-3-large`). Real benchmark runs pin a real backend;
    the offline demo uses `local-hash`.
    """
    if spec in ("", "local-hash"):
        return LocalDeterministicEmbedder()
    if spec.startswith("voyage"):
        _, _, model = spec.partition(":")
        return VoyageEmbedder(model or "voyage-4-large")
    if spec.startswith("st"):
        _, _, model = spec.partition(":")
        return SentenceTransformerEmbedder(model or "all-MiniLM-L6-v2")
    if spec.startswith("litellm"):
        _, _, model = spec.partition(":")
        return LiteLLMEmbedder(model or "text-embedding-3-large")
    raise ValueError(f"unknown embedder spec: {spec!r}")
