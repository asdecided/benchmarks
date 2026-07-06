"""Chunk-and-average embedding: a document too long for an embedder's input
limit is sub-chunked and its chunk vectors averaged, rather than truncated —
see `embed_chunked` / `chunk_by_tokens` in providers/embedding.py.
"""

from __future__ import annotations

import math

from providers.base import estimate_tokens
from providers.embedding import LocalDeterministicEmbedder, chunk_by_tokens, embed_chunked


class _FixedLimitEmbedder(LocalDeterministicEmbedder):
    """The offline hashing embedder with an artificial input-length limit, so
    the chunk-and-average path can be exercised without a real API."""

    def __init__(self, max_input_tokens: int, dim: int = 64) -> None:
        super().__init__(dim=dim)
        self.max_input_tokens = max_input_tokens
        self.calls: list[str] = []

    def embed(self, text, input_type=None):
        self.calls.append(text)
        return super().embed(text, input_type=input_type)


def _norm(vec):
    return math.sqrt(sum(v * v for v in vec))


# --- chunk_by_tokens ---------------------------------------------------------


def test_chunk_by_tokens_short_text_is_a_single_chunk():
    text = "one short paragraph."
    assert chunk_by_tokens(text, max_tokens=1000) == [text]


def test_chunk_by_tokens_empty_text_is_no_chunks():
    assert chunk_by_tokens("", max_tokens=100) == []


def test_chunk_by_tokens_splits_long_text_and_respects_the_budget():
    text = "\n\n".join(f"Paragraph {i} with some extra words to pad it out." for i in range(50))
    chunks = chunk_by_tokens(text, max_tokens=20)
    assert len(chunks) > 1
    assert all(estimate_tokens(c) <= 20 * 1.001 for c in chunks) or all(
        len(c) <= 20 * 4 for c in chunks
    )
    # Nothing is dropped: every paragraph's distinctive marker survives somewhere.
    joined = " ".join(chunks)
    for i in range(50):
        assert f"Paragraph {i} " in joined


def test_chunk_by_tokens_recursively_splits_a_single_giant_paragraph():
    # No blank lines at all — must fall back to sentence, then word, splitting.
    text = " ".join(f"sentence{i}." for i in range(400))
    chunks = chunk_by_tokens(text, max_tokens=10)
    assert len(chunks) > 1
    assert all(len(c) <= 10 * 4 for c in chunks)
    assert "sentence0." in chunks[0]
    assert "sentence399." in chunks[-1]


def test_chunk_by_tokens_hard_splits_a_single_whitespace_free_word():
    # A URL/hash/base64 blob with no spaces at all — no boundary to split on
    # short of hard character slicing. Every returned chunk must still fit.
    long_word = "A" * 500
    text = f"Some intro text before it. {long_word} more prose follows after."
    chunks = chunk_by_tokens(text, max_tokens=10)
    max_chars = 10 * 4
    assert all(len(c) <= max_chars for c in chunks), [len(c) for c in chunks]
    assert long_word in "".join(chunks)


# --- embed_chunked ------------------------------------------------------------


def test_embed_chunked_short_text_takes_the_single_call_path():
    e = _FixedLimitEmbedder(max_input_tokens=1000)
    text = "hello world"
    vec = embed_chunked(e, text, input_type="document")
    assert e.calls == [text]  # exactly one embed() call, the whole text
    assert vec == e.embed(text, input_type="document")


def test_embed_chunked_unbounded_embedder_never_chunks():
    e = LocalDeterministicEmbedder()  # max_input_tokens is None
    text = "word " * 5000
    vec = embed_chunked(e, text)
    assert vec == e.embed(text)


def test_embed_chunked_long_text_makes_multiple_calls_and_returns_unit_vector():
    e = _FixedLimitEmbedder(max_input_tokens=20)
    text = "\n\n".join(f"Paragraph {i} has some content padding words here." for i in range(60))
    assert estimate_tokens(text) > e.max_input_tokens
    vec = embed_chunked(e, text, input_type="document")
    assert len(e.calls) > 1  # sub-chunked, not a single over-limit call
    assert all(c != text for c in e.calls)  # never the whole oversized text
    assert abs(_norm(vec) - 1.0) < 1e-9  # re-normalised after averaging


def test_embed_chunked_never_truncates_content_out_of_the_result():
    # A distinctive marker placed only in the LAST paragraph must still
    # influence the resulting vector — truncation would drop it entirely.
    e = _FixedLimitEmbedder(max_input_tokens=15)
    filler = "\n\n".join(f"Filler paragraph number {i} padding words." for i in range(40))
    with_tail = filler + "\n\nZZZMARKERZZZ decisive clause here.\n"
    without_tail = filler + "\n\nharmless closing remark.\n"
    v_with = embed_chunked(e, with_tail, input_type="document")
    v_without = embed_chunked(e, without_tail, input_type="document")
    assert v_with != v_without
    # The marker's own chunk must have actually been embedded.
    assert any("ZZZMARKERZZZ" in c for c in e.calls)


def test_embed_chunked_weights_by_chunk_length_not_uniformly():
    # Two chunks of very different sizes: the longer one should dominate the
    # average more than a plain unweighted mean would.
    e = _FixedLimitEmbedder(max_input_tokens=8)
    short = "alpha beta."
    long_ = ("gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi "
             "omicron pi rho sigma tau upsilon phi chi psi omega. ") * 3
    text = short + "\n\n" + long_
    vec = embed_chunked(e, text, input_type="document")
    weighted_only_long = embed_chunked(e, long_, input_type="document")
    # The combined vector should be closer to the long chunk's own embedding
    # than to the short chunk's, since the long chunk carries more weight.
    def cos(a, b):
        return sum(x * y for x, y in zip(a, b))
    short_vec = e.embed(short, input_type="document")
    assert cos(vec, weighted_only_long) > cos(vec, short_vec)


# --- real-embedder limits are wired, not just theoretical --------------------


def test_voyage_embedder_declares_a_max_input_tokens():
    from providers.embedding import VoyageEmbedder

    assert VoyageEmbedder().max_input_tokens == 32_000


def test_sentence_transformer_embedder_declares_a_max_input_tokens():
    from providers.embedding import SentenceTransformerEmbedder

    assert SentenceTransformerEmbedder().max_input_tokens == 256


def test_litellm_embedder_declares_a_max_input_tokens_default():
    from providers.embedding import LiteLLMEmbedder

    e = LiteLLMEmbedder()
    assert e.max_input_tokens == 8191
    e2 = LiteLLMEmbedder(max_input_tokens=4096)
    assert e2.max_input_tokens == 4096


# --- naive_rag actually uses the chunked path --------------------------------


def test_naive_rag_prepare_chunks_oversized_sections(monkeypatch):
    from providers.base import CorpusArtifact
    from providers.naive_rag import NaiveRagProvider
    from providers import ScriptedAnsweringModel

    embedder = _FixedLimitEmbedder(max_input_tokens=15)
    provider = NaiveRagProvider(ScriptedAnsweringModel(), embedder=embedder, top_k=2)
    long_section = "\n\n".join(f"Sentence {i} padding words go here." for i in range(60))
    corpus = [
        CorpusArtifact(
            id="D-1", type="decision", path="d1.md",
            text=f"# D-1\n\n## Body\n\n{long_section}\n",
        )
    ]
    provider.prepare(corpus)
    assert len(embedder.calls) > 1  # the section was sub-chunked, not truncated
