# SPDX-License-Identifier: Apache-2.0
"""Shared, engine-free helpers for the scale evidence member.

Both the corpus generator and the latency harness import this module so that
artifact ids and query vocabulary are derived the *same* deterministic way on
both sides — the generator writes an id, the harness re-derives the identical
id to resolve it, with no lookup and no shared state on disk.

Nothing here imports the engine (DG-ADR-0001): ``rac`` is only ever an
external CLI on ``PATH``. Stdlib only.
"""

from __future__ import annotations

# Crockford base32, the alphabet the engine's id syntax accepts
# (<KEY>-<12-char Crockford base32 suffix>). Excludes I, L, O, U.
_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# The scale corpus fixes the repository key at RAC and reserves a recognisable
# "SCA" lead in the 12-char suffix, leaving nine base32 digits of counter —
# 32**9 ≈ 3.5e13 distinct ids, ample past the 1M reference target.
ID_KEY = "RAC"
_ID_TAG = "SCA"
_COUNTER_WIDTH = 9


def _encode(counter: int, width: int) -> str:
    """Zero-padded Crockford base32 of ``counter`` at a fixed width."""
    if counter < 0:
        raise ValueError("counter must be non-negative")
    digits = []
    for _ in range(width):
        counter, rem = divmod(counter, 32)
        digits.append(_ALPHABET[rem])
    if counter:
        raise ValueError(f"counter overflows {width} base32 digits")
    return "".join(reversed(digits))


def artifact_id(index: int) -> str:
    """The deterministic canonical id for the artifact at ``index``.

    Example: ``artifact_id(0) -> 'RAC-SCA000000000'``. The id is a pure
    function of the index, so the harness reconstructs any generated id
    without reading the corpus.
    """
    return f"{ID_KEY}-{_ID_TAG}{_encode(index, _COUNTER_WIDTH)}"


# The proportion mix, in id-range order. Decisions come first so a
# requirement can reference a decision id that is guaranteed to already exist.
TYPE_MIX = (
    ("decision", 0.25),
    ("requirement", 0.55),
    ("roadmap", 0.10),
    ("prompt", 0.05),
    ("design", 0.05),
)

# Short, stable filename prefixes per type.
TYPE_PREFIX = {
    "decision": "dec",
    "requirement": "req",
    "roadmap": "road",
    "prompt": "prompt",
    "design": "design",
}

FILES_PER_SHARD = 2000


def type_layout(count: int) -> list[tuple[str, int, int]]:
    """Contiguous ``(type, start, end)`` index ranges for a corpus of ``count``.

    Deterministic and independent of the machine: every non-requirement type
    is rounded from its share, and ``requirement`` — the largest slice —
    absorbs the remainder so the ranges always tile ``[0, count)`` exactly.
    """
    if count < 0:
        raise ValueError("count must be non-negative")
    sizes: dict[str, int] = {}
    for name, share in TYPE_MIX:
        if name == "requirement":
            continue
        sizes[name] = round(count * share)
    non_req = sum(sizes.values())
    sizes["requirement"] = max(0, count - non_req)
    # Guard: if rounding overshot a tiny corpus, trim from requirement then
    # from the largest non-requirement bucket, so the total is exact.
    overshoot = sum(sizes.values()) - count
    while overshoot > 0:
        victim = max(sizes, key=lambda k: sizes[k])
        sizes[victim] -= 1
        overshoot -= 1

    layout: list[tuple[str, int, int]] = []
    cursor = 0
    for name, _share in TYPE_MIX:
        n = sizes[name]
        layout.append((name, cursor, cursor + n))
        cursor += n
    return layout


def type_of(index: int, layout: list[tuple[str, int, int]]) -> str:
    for name, start, end in layout:
        if start <= index < end:
            return name
    raise IndexError(index)


def decision_range(layout: list[tuple[str, int, int]]) -> tuple[int, int]:
    for name, start, end in layout:
        if name == "decision":
            return start, end
    return (0, 0)


def shard_dir(index: int) -> str:
    return f"shard-{index // FILES_PER_SHARD:03d}"


# --- Deterministic vocabulary --------------------------------------------
#
# Every token here is a discriminating search term: the generator sprinkles a
# per-artifact subset into titles and bodies, and the harness draws warm-query
# terms from the same lists, so an MCP search is guaranteed to hit real
# matches without the two sides sharing anything but this module.

TOPICS = (
    "ingestion", "throughput", "caching", "retrieval", "sharding",
    "indexing", "validation", "relationships", "supersession", "provenance",
    "telemetry", "grounding", "export", "portfolio", "watchkeeper",
    "normalisation", "classification", "traceability", "resolution", "roadmap",
    "capture", "federation", "connectors", "embeddings", "latency",
    "memory", "concurrency", "streaming", "pagination", "compression",
    "checksum", "manifest", "scaffold", "onboarding", "enforcement",
    "audit", "airgap", "enterprise", "namespace", "lifecycle",
)

SUBSYSTEMS = (
    "parser", "scanner", "registry", "resolver", "walker",
    "linter", "graph", "cache-layer", "server", "client",
    "exporter", "importer", "planner", "collector", "emitter",
    "matcher", "ranker", "budgeter", "auditor", "packager",
)

ADJECTIVES = (
    "deterministic", "incremental", "buffered", "sharded", "streaming",
    "content-addressed", "offline", "read-only", "typed", "thin",
    "layered", "warm", "cold", "flat", "bounded",
    "reproducible", "canonical", "derived", "stateless", "vendored",
)

VERBS = (
    "ingest", "resolve", "validate", "shard", "index",
    "export", "cache", "stream", "classify", "normalise",
    "audit", "compress", "checksum", "paginate", "materialise",
)

# One flat, order-stable term pool the harness pulls distinct queries from.
QUERY_TERMS = TOPICS + SUBSYSTEMS + ADJECTIVES
