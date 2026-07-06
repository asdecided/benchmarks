# SPDX-License-Identifier: Apache-2.0
"""A deterministic, streaming BM25 ranker over a canon document's chunks.

The canon arm treats a monolithic document the way a team actually would: chunk
it by its own heading structure — the strongest simple treatment such a
document supports (roadmap Risks: no strawman chunker) — and rank the chunks
lexically. There is deliberately NO liveness or supersession logic here: a
document has no typed identity for the engine's live filter to read, so a
superseded block ranks on its text like any other. That absence is the point
the benchmark measures.

Tokenisation is plain and documented: lowercase, then split on any
non-alphanumeric boundary (``[a-z0-9]+``). That is the token-boundary rule the
engine's own search matches on (ADR-037), so both arms rank on the same lexical
family and granularity — not tokenisation — is the variable.

Both passes stream the file: one chunk of text is held at a time, never the
whole canon (a 100k canon is hundreds of MB). Pass one accumulates document
frequencies over the small bounded vocabulary; pass two scores each chunk and
keeps, per query, only matched ``(score, order, id)`` triples — bounded by the
match set, never by the canon's byte size.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from pathlib import Path
from typing import Iterator

_TOKEN = re.compile(r"[a-z0-9]+")
_ID = re.compile(r"RAC-[0-9A-Z]+")
_HEADING = re.compile(r"^## (?!#)")  # a canon block heading: exactly '## '

# Standard Okapi BM25 constants.
_K1 = 1.5
_B = 0.75


def tokenize(text: str) -> list[str]:
    """Lowercase, split on non-alphanumeric — the documented shared rule."""
    return _TOKEN.findall(text.lower())


def iter_chunks(path: Path) -> Iterator[tuple[str, str]]:
    """Stream ``(id, chunk_text)`` per ``##`` block; one block in memory at a time.

    The heading line carries the id (``## <id> — <title>``); a block runs to the
    next heading or EOF. Text before the first heading (the document's own H1
    preamble) is skipped.
    """
    buf: list[str] = []
    cur_id: str | None = None
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            if _HEADING.match(line):
                if cur_id is not None:
                    yield cur_id, "".join(buf)
                buf = [line]
                m = _ID.search(line)
                cur_id = m.group(0) if m else None
            elif cur_id is not None:
                buf.append(line)
    if cur_id is not None:
        yield cur_id, "".join(buf)


class _Corpus:
    """Streaming BM25 statistics for one canon file (bounded-vocabulary df)."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.n_docs = 0
        self.total_len = 0
        self.df: Counter[str] = Counter()
        for _id, text in iter_chunks(path):
            tokens = tokenize(text)
            self.n_docs += 1
            self.total_len += len(tokens)
            for term in set(tokens):
                self.df[term] += 1
        self.avgdl = (self.total_len / self.n_docs) if self.n_docs else 0.0

    def idf(self, term: str) -> float:
        # Okapi BM25 idf with the +1 shift so it is always non-negative.
        n = self.df.get(term, 0)
        return math.log(1 + (self.n_docs - n + 0.5) / (n + 0.5))


def rank(path: Path, queries: dict[str, list[str]]) -> dict[str, list[str]]:
    """Rank every canon chunk per query; return ``{query_id: [ids, best-first]}``.

    ``queries`` maps a query id to its token list. One streaming pass over the
    canon scores each chunk against every query; a chunk enters a query's result
    list only if it matches at least one query term (score > 0). Ties break by
    document order, so the ranking is fully deterministic.
    """
    corpus = _Corpus(path)
    # Precompute per-query idf weights once.
    weights: dict[str, dict[str, float]] = {
        qid: {t: corpus.idf(t) for t in set(tokens)} for qid, tokens in queries.items()
    }
    hits: dict[str, list[tuple[float, int, str]]] = {qid: [] for qid in queries}

    for order, (doc_id, text) in enumerate(iter_chunks(path)):
        tokens = tokenize(text)
        dl = len(tokens)
        tf = Counter(tokens)
        denom_len = _K1 * (1 - _B + _B * (dl / corpus.avgdl if corpus.avgdl else 0))
        for qid, qweights in weights.items():
            score = 0.0
            for term, idf in qweights.items():
                f = tf.get(term, 0)
                if f:
                    score += idf * (f * (_K1 + 1)) / (f + denom_len)
            if score > 0.0:
                hits[qid].append((score, order, doc_id))

    ranked: dict[str, list[str]] = {}
    for qid, triples in hits.items():
        # Highest score first; document order breaks ties (ascending order).
        triples.sort(key=lambda t: (-t[0], t[1]))
        ranked[qid] = [doc_id for _score, _order, doc_id in triples]
    return ranked
