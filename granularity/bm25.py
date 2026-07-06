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
from typing import Callable, Iterator

_TOKEN = re.compile(r"[a-z0-9]+")
_ID = re.compile(r"RAC-[0-9A-Z]+")
_HEADING = re.compile(r"^## (?!#)")  # a canon block heading: exactly '## '
_FRONT_ID = re.compile(r"^id:\s*(RAC-[0-9A-Z]+)\s*$", re.MULTILINE)
_FRONT_TYPE = re.compile(r"^type:\s*(\w+)\s*$", re.MULTILINE)
# A canon block's ``### Status`` section (H3 nested under the ``##`` block).
_STATUS_HEADING = re.compile(r"^### Status\s*$", re.MULTILINE)

# Standard Okapi BM25 constants.
_K1 = 1.5
_B = 0.75

# A chunk source is a zero-argument callable returning a fresh ``(id, text)``
# stream. BM25 needs two passes (document frequencies, then scoring), so the
# ranker asks the source for a new iterator per pass rather than materialising
# the whole stream — the canon variant and the per-artifact variant both plug
# into the identical ranker this way (one ranker, one variable: granularity).
ChunkSource = Callable[[], Iterator[tuple[str, str]]]


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


def _frontmatter(text: str) -> tuple[str | None, str | None]:
    """``(id, type)`` from a per-file artifact's leading ``---`` block, else Nones."""
    if not text.startswith("---"):
        return None, None
    end = text.find("\n---", 3)
    block = text if end == -1 else text[:end]
    idm = _FRONT_ID.search(block)
    tm = _FRONT_TYPE.search(block)
    return (idm.group(1) if idm else None, tm.group(1) if tm else None)


def iter_artifact_chunks(
    artifacts_dir: Path, only_type: str | None = None
) -> Iterator[tuple[str, str]]:
    """Stream ``(id, whole-file-text)`` — one chunk per per-file artifact.

    Files are visited in sorted relative-path order so the tie-break domain is
    stable and reproducible. For the granularity twin of a decisions canon this
    is decision files only (``only_type='decision'``), whose zero-padded
    ``dec-<index>.md`` names sort into the same index order the canon streams —
    the residual difference from canon document order is that path sort, not
    stream position, fixes ties (README documents it). One file is held in
    memory at a time, so nothing is bounded by the corpus's total byte size.
    """
    for path in sorted(artifacts_dir.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        fid, ftype = _frontmatter(text)
        if fid is None:
            continue
        if only_type is not None and ftype != only_type:
            continue
        yield fid, text


def _is_superseded(chunk_text: str) -> bool:
    """True when a canon block's ``### Status`` first non-empty line is ``Superseded``.

    The canon rendering carries each retired block's verbatim status line as
    plain text (``### Status`` / ``Superseded``); a status-aware reader parses it
    deterministically. Anything else — ``Accepted``, a missing status, or a
    section that runs straight into the next heading — is treated as live.
    """
    m = _STATUS_HEADING.search(chunk_text)
    if m is None:
        return False
    for line in chunk_text[m.end() :].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):  # next heading before any status text
            return False
        return stripped == "Superseded"
    return False


def iter_live_chunks(path: Path) -> Iterator[tuple[str, str]]:
    """``iter_chunks`` with superseded blocks dropped — the strongest honest canon.

    A team that reads the status line it already rendered would never surface a
    retired block; this filter models exactly that and nothing more.
    """
    for doc_id, text in iter_chunks(path):
        if _is_superseded(text):
            continue
        yield doc_id, text


class _Corpus:
    """Streaming BM25 statistics for one chunk source (bounded-vocabulary df)."""

    def __init__(self, chunks: ChunkSource) -> None:
        self.n_docs = 0
        self.total_len = 0
        self.df: Counter[str] = Counter()
        for _id, text in chunks():
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


def rank_chunks(
    chunks: ChunkSource, queries: dict[str, list[str]]
) -> dict[str, list[str]]:
    """Rank every chunk from ``chunks`` per query; ``{query_id: [ids, best-first]}``.

    ``queries`` maps a query id to its token list. One streaming pass over the
    chunk source scores each chunk against every query; a chunk enters a query's
    result list only if it matches at least one query term (score > 0). Ties
    break by streaming order, so the ranking is fully deterministic. This is the
    one ranker every canon-family arm shares — only the chunk source (a whole
    canon, its live-only subset, or the per-file artifacts) varies.
    """
    corpus = _Corpus(chunks)
    # Precompute per-query idf weights once.
    weights: dict[str, dict[str, float]] = {
        qid: {t: corpus.idf(t) for t in set(tokens)} for qid, tokens in queries.items()
    }
    hits: dict[str, list[tuple[float, int, str]]] = {qid: [] for qid in queries}

    for order, (doc_id, text) in enumerate(chunks()):
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
        # Highest score first; streaming order breaks ties (ascending order).
        triples.sort(key=lambda t: (-t[0], t[1]))
        ranked[qid] = [doc_id for _score, _order, doc_id in triples]
    return ranked


def rank(path: Path, queries: dict[str, list[str]]) -> dict[str, list[str]]:
    """Rank every canon chunk per query — the canon arm's convenience entry point."""
    return rank_chunks(lambda: iter_chunks(path), queries)
