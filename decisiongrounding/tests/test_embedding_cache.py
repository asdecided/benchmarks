"""Content-hash embedding cache: identical backend calls are served from
cache — results-neutral by construction, only cost/wall-clock change."""

from pathlib import Path

import pytest

import providers.embedding as embedding
from providers.embedding import (
    Embedder,
    LocalDeterministicEmbedder,
    embed_chunked,
    get_embedding_cache,
    reset_embedding_cache,
)

_ROOT = Path(__file__).resolve().parent.parent
_SCENARIOS = _ROOT / "scenarios"


class CountingEmbedder(Embedder):
    """Deterministic fake real backend that counts every backend call."""

    max_input_tokens = None

    def __init__(self, name="counting-test-1", dim=4, max_input_tokens=None):
        self.name = name
        self.dim = dim
        self.max_input_tokens = max_input_tokens
        self.calls = 0

    def embed(self, text, input_type=None):
        self.calls += 1
        vec = [0.0] * self.dim
        vec[0] = 1.0
        return vec


@pytest.fixture(autouse=True)
def _isolated_cache(monkeypatch):
    monkeypatch.delenv("DG_EMBED_CACHE", raising=False)
    monkeypatch.delenv("DG_EMBED_CACHE_DIR", raising=False)
    reset_embedding_cache()
    yield
    reset_embedding_cache()


def test_cache_hit_skips_backend():
    emb = CountingEmbedder()
    v1 = embed_chunked(emb, "the same text", input_type="document")
    v2 = embed_chunked(emb, "the same text", input_type="document")
    assert emb.calls == 1
    assert v1 == v2
    assert get_embedding_cache().hits == 1


def test_input_type_and_text_are_part_of_the_key():
    emb = CountingEmbedder()
    embed_chunked(emb, "same text", input_type="query")
    embed_chunked(emb, "same text", input_type="document")
    assert emb.calls == 2
    embed_chunked(emb, "different text", input_type="query")
    assert emb.calls == 3


def test_embedder_name_is_part_of_the_key():
    a = CountingEmbedder(name="model-a")
    b = CountingEmbedder(name="model-b")
    embed_chunked(a, "shared text")
    embed_chunked(b, "shared text")
    assert a.calls == 1 and b.calls == 1  # no cross-model hit


def test_local_hash_embedder_not_cached():
    emb = LocalDeterministicEmbedder()
    embed_chunked(emb, "some text")
    embed_chunked(emb, "some text")
    cache = get_embedding_cache()
    assert cache.hits == 0 and cache.misses == 0 and cache.stats()["entries"] == 0


def test_disabled_via_env(monkeypatch):
    monkeypatch.setenv("DG_EMBED_CACHE", "0")
    reset_embedding_cache()
    assert get_embedding_cache() is None
    emb = CountingEmbedder()
    embed_chunked(emb, "text")
    embed_chunked(emb, "text")
    assert emb.calls == 2


def test_disk_layer_persists_across_cache_instances(tmp_path, monkeypatch):
    monkeypatch.setenv("DG_EMBED_CACHE_DIR", str(tmp_path))
    reset_embedding_cache()
    emb = CountingEmbedder()
    embed_chunked(emb, "durable text")
    assert emb.calls == 1
    key_files = list(tmp_path.rglob("*.json"))
    assert len(key_files) == 1

    reset_embedding_cache()  # fresh memory layer — only disk survives
    embed_chunked(emb, "durable text")
    assert emb.calls == 1  # served from disk


def test_chunked_document_cached_per_piece():
    emb = CountingEmbedder(max_input_tokens=10)
    long_text = " ".join(f"word{i}" for i in range(200))
    embed_chunked(emb, long_text, input_type="document")
    n_pieces = emb.calls
    assert n_pieces > 1
    embed_chunked(emb, long_text, input_type="document")
    assert emb.calls == n_pieces  # every piece a hit on the second pass


def test_dim_backfilled_on_all_hit_run():
    warm = CountingEmbedder(name="probe-model", dim=4)
    embed_chunked(warm, "probe text")
    cold = CountingEmbedder(name="probe-model", dim=0)  # dim not probed yet
    embed_chunked(cold, "probe text")
    assert cold.calls == 0
    assert cold.dim == 4


def test_naive_rag_reprepare_reuses_embeddings():
    from providers import ScriptedAnsweringModel
    from providers.naive_rag import NaiveRagProvider
    from scenarios.loader import load_scenarios

    sc = load_scenarios(_SCENARIOS)[0]
    emb = CountingEmbedder()
    provider = NaiveRagProvider(ScriptedAnsweringModel(seed=0), embedder=emb)
    provider.prepare(list(sc.corpus))
    first = emb.calls
    assert first > 0
    provider.prepare(list(sc.corpus))
    assert emb.calls == first  # the whole second prepare served from cache
