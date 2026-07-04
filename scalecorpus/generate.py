#!/usr/bin/env python3
"""Deterministic RAC scale-corpus generator.

Emits a synthetic RAC corpus of N artifacts (requirement / decision / roadmap /
prompt / design) that classify and validate under `rac validate`. The corpus is
a pure function of (size, seed): every byte is derived from the artifact index,
so any two runs — on any machine, with any worker count — produce identical
trees. That determinism is the point: benchmark numbers taken on "the 1M
corpus" refer to one exact set of bytes.

Layout: files are sharded 1,000 per directory (shard-00000/, shard-00001/, ...)
so no directory ever holds an unbounded file count.

Query design: the vocabulary is bounded and stratified so retrieval benchmarks
can pick terms with known selectivity —
  - COMMON terms appear in roughly a third of artifacts (worst-case postings),
  - MID terms in roughly 2% of artifacts,
  - RARE terms in roughly 0.05% of artifacts (selective lookups),
and every artifact's ID resolves via `rac resolve` (point lookups).

Usage:
  python generate.py --size 100000 --out /path/to/corpus [--seed 7] [--workers 4]
"""

from __future__ import annotations

import argparse
import hashlib
import multiprocessing
import os
import random
import shutil
import sys
import time
from pathlib import Path

SHARD_SIZE = 1000

TYPES = ["requirement", "decision", "roadmap", "prompt", "design"]
# Cumulative weights: requirement 30%, decision 30%, roadmap 10%, prompt 15%, design 15%.
TYPE_CUM = [(0.30, "requirement"), (0.60, "decision"), (0.70, "roadmap"), (0.85, "prompt"), (1.00, "design")]

HEADING = {
    "requirement": "Requirement",
    "decision": "ADR",
    "roadmap": "Roadmap",
    "prompt": "Prompt",
    "design": "Design",
}

RELATED_SECTION = {
    "requirement": "Related Requirements",
    "decision": "Related Decisions",
    "roadmap": "Related Roadmaps",
    "prompt": "Related Prompts",
    "design": "Related Designs",
}

# Bounded, stratified vocabulary. Frequencies are enforced by draw probability,
# not by the word lists' lengths.
COMMON = (
    "pipeline artifact corpus validation schema markdown deterministic "
    "repository index release contract workflow traceability lifecycle "
    "metadata frontmatter classification relationship coverage export"
).split()
MID = (
    "watchkeeper gatekeeper registrar explorer ingest connector telemetry "
    "portfolio quickstart doctor drift resolver snapshot ledger provenance "
    "revision materialization conformance normalisation adjacency batching "
    "checkpoint quorum staleness idempotency backfill"
).split()
RARE = (
    "zanzibar quillwort ossify vermilion palimpsest thaumatrope archipelago "
    "cormorant isthmus breccia solfeggio dirigible mangrove ozokerite "
    "petrichor sastrugi tessellate umbriel wainscot xenolith"
).split()

VERBS = "records tracks validates exposes derives resolves gates publishes indexes reconciles".split()
NOUNS = "team platform agent reviewer maintainer operator auditor customer analyst integrator".split()


def artifact_type(i: int) -> str:
    """Type is a pure function of the index so cross-references can name the
    correct related-section without materializing the target."""
    r = _unit(i, "type")
    for cum, t in TYPE_CUM:
        if r <= cum:
            return t
    return "design"


def _unit(i: int, salt: str) -> float:
    """Deterministic uniform [0,1) from (index, salt) — platform-stable."""
    h = hashlib.blake2b(f"{salt}:{i}".encode(), digest_size=8).digest()
    return int.from_bytes(h, "big") / 2**64


def artifact_id(i: int) -> str:
    return f"RAC-SC{i:010d}"


def _rng(seed: int, i: int) -> random.Random:
    return random.Random(f"{seed}:{i}")


def _sentence(rng: random.Random) -> str:
    words = [rng.choice(COMMON) for _ in range(rng.randint(4, 8))]
    if rng.random() < 0.30:
        words.insert(rng.randrange(len(words)), rng.choice(MID) if rng.random() < 0.96 else rng.choice(RARE))
    return (
        f"The {rng.choice(NOUNS)} {rng.choice(VERBS)} the "
        + " ".join(words[:3])
        + f" so the {rng.choice(NOUNS)} can rely on "
        + " ".join(words[3:])
        + "."
    )


def _paragraph(rng: random.Random, n: int) -> str:
    return " ".join(_sentence(rng) for _ in range(n))


def _term_block(rng: random.Random, i: int) -> str:
    """Controlled-selectivity terms: MID in ~2% of docs, RARE in ~0.05%."""
    parts = []
    if _unit(i, "mid") < 0.02:
        parts.append(f"This work concerns the {MID[int(_unit(i, 'midpick') * len(MID))]} surface.")
    if _unit(i, "rare") < 0.0005:
        parts.append(f"Archival keyword: {RARE[int(_unit(i, 'rarepick') * len(RARE))]}.")
    return " ".join(parts)


# Which target types each source type may relate to (mirrors the rac-core
# artifact specs; an edge outside this matrix is a validation warning).
ALLOWED_TARGETS = {
    "requirement": {"decision", "design", "prompt", "requirement", "roadmap"},
    "decision": {"decision", "design", "requirement", "roadmap"},
    "roadmap": {"decision", "design", "prompt", "requirement", "roadmap"},
    "prompt": {"decision", "design", "requirement", "roadmap"},
    "design": {"decision", "prompt", "requirement", "roadmap"},
}


def _references(rng: random.Random, i: int, source_type: str) -> dict[str, list[str]]:
    """0-5 references to strictly earlier artifacts, grouped by target type."""
    if i == 0:
        return {}
    allowed = ALLOWED_TARGETS[source_type]
    refs: dict[str, list[str]] = {}
    for _ in range(rng.randint(0, 5)):
        j = rng.randrange(0, i)
        t = artifact_type(j)
        if t in allowed:
            refs.setdefault(t, []).append(artifact_id(j))
    return {t: sorted(set(ids)) for t, ids in refs.items()}


def _related_sections(refs: dict[str, list[str]]) -> str:
    out = []
    for t in TYPES:
        if t in refs:
            out.append(f"## {RELATED_SECTION[t]}\n")
            out.extend(f"- {rid}" for rid in refs[t])
            out.append("")
    return "\n".join(out)


def _title(rng: random.Random, i: int) -> str:
    return (
        f"{rng.choice(COMMON).capitalize()} {rng.choice(MID)} "
        f"{rng.choice(COMMON)} {i}"
    )


def render(i: int, seed: int) -> tuple[str, str]:
    """Return (relative path, file content) for artifact index i."""
    t = artifact_type(i)
    rng = _rng(seed, i)
    aid = artifact_id(i)
    title = _title(rng, i)
    refs = _references(rng, i, t)
    extra = _term_block(rng, i)

    head = f"---\nschema_version: 1\nid: {aid}\ntype: {t}\n---\n# {HEADING[t]}: {title}\n"
    status = "## Status\n\nAccepted\n"

    if t == "requirement":
        n_reqs = rng.randint(2, 4)
        reqs = "\n".join(
            f"- [REQ-{k:03d}] The system {rng.choice(VERBS)} the {rng.choice(COMMON)} {rng.choice(COMMON)}."
            for k in range(1, n_reqs + 1)
        )
        body = (
            f"{status}\n## Problem\n\n{_paragraph(rng, 3)} {extra}\n\n"
            f"## Requirements\n\n{reqs}\n\n"
            f"## Success Metrics\n\n{_paragraph(rng, 2)}\n"
        )
    elif t == "decision":
        body = (
            f"{status}\n## Category\n\nTechnical\n\n"
            f"## Context\n\n{_paragraph(rng, 3)} {extra}\n\n"
            f"## Decision\n\n{_paragraph(rng, 2)}\n\n"
            f"## Consequences\n\n{_paragraph(rng, 2)}\n"
        )
    elif t == "roadmap":
        status = "## Status\n\nPlanned\n"
        body = (
            f"{status}\n## Outcomes\n\n{_paragraph(rng, 2)} {extra}\n\n"
            f"## Initiatives\n\n- {_sentence(rng)}\n- {_sentence(rng)}\n\n"
            f"## Success Measures\n\n{_paragraph(rng, 2)}\n"
        )
    elif t == "prompt":
        body = (
            f"## Objective\n\n{_paragraph(rng, 2)} {extra}\n\n"
            f"## Input\n\n{_paragraph(rng, 1)}\n\n"
            f"## Instructions\n\n- {_sentence(rng)}\n- {_sentence(rng)}\n\n"
            f"## Output\n\n{_paragraph(rng, 1)}\n"
        )
    else:  # design
        body = (
            f"## Context\n\n{_paragraph(rng, 2)} {extra}\n\n"
            f"## User Need\n\n{_paragraph(rng, 1)}\n\n"
            f"## Design\n\n{_paragraph(rng, 2)}\n\n"
            f"## Constraints\n\n{_paragraph(rng, 1)}\n"
        )

    related = _related_sections(refs)
    content = head + "\n" + body + ("\n" + related if related else "")
    shard = i // SHARD_SIZE
    rel = f"shard-{shard:05d}/{t[:3]}-{i:010d}.md"
    return rel, content


def _write_range(args: tuple[int, int, int, str]) -> int:
    start, end, seed, out = args
    root = Path(out)
    last_shard = -1
    for i in range(start, end):
        rel, content = render(i, seed)
        p = root / rel
        shard = i // SHARD_SIZE
        if shard != last_shard:
            p.parent.mkdir(parents=True, exist_ok=True)
            last_shard = shard
        p.write_bytes(content.encode())
    return end - start


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--size", type=int, required=True, help="artifact count")
    ap.add_argument("--out", required=True, help="output directory (created; must be empty or absent)")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 1)
    ap.add_argument("--force", action="store_true", help="delete an existing output directory first")
    a = ap.parse_args()

    out = Path(a.out)
    if out.exists():
        if not a.force:
            print(f"refusing to write into existing {out} (use --force)", file=sys.stderr)
            return 2
        shutil.rmtree(out)
    out.mkdir(parents=True)

    t0 = time.monotonic()
    # Ranges are shard-aligned so no two workers touch one directory.
    per = max(SHARD_SIZE, (a.size // a.workers // SHARD_SIZE) * SHARD_SIZE)
    ranges = []
    s = 0
    while s < a.size:
        e = min(a.size, s + per)
        ranges.append((s, e, a.seed, str(out)))
        s = e
    if a.workers > 1 and len(ranges) > 1:
        with multiprocessing.Pool(a.workers) as pool:
            done = sum(pool.imap_unordered(_write_range, ranges))
    else:
        done = sum(_write_range(r) for r in ranges)
    dt = time.monotonic() - t0
    print(f"wrote {done} artifacts to {out} in {dt:.1f}s ({done/max(dt,1e-9):.0f}/s), seed={a.seed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
