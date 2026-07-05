#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Deterministic scale-corpus generator for the RAC engine.

Emits N valid RAC artifacts — a realistic type mix that classifies as, and
passes ``rac validate`` / ``rac relationships --validate`` for, its declared
type — into a sharded directory tree. Output is byte-identical for identical
``(count, seed)``: every artifact's content is a pure function of its index
under a seeded :class:`random.Random`, so nothing depends on the wall clock or
on filesystem iteration order.

    python scale/generate_corpus.py --count N --out DIR [--seed 42] [--manifest]

This is generator tooling for an evidence run, not an engine consumer: it never
imports ``rac`` (DG-ADR-0001). ``rac`` is exercised separately by ``measure.py``
as an external CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402  (local module, path-injected above)
    FILES_PER_SHARD,
    TYPE_PREFIX,
    ADJECTIVES,
    SUBSYSTEMS,
    TOPICS,
    VERBS,
    artifact_id,
    decision_range,
    shard_dir,
    type_layout,
    type_of,
)


def _rng(seed: int, index: int) -> random.Random:
    """A per-artifact RNG keyed only on ``(seed, index)``.

    A string seed makes the stream independent of ``PYTHONHASHSEED`` (CPython
    derives the state from a hash of the seed bytes), so the same index yields
    the same words on every machine and in any generation order.
    """
    return random.Random(f"{seed}:{index}")


def _words(rng: random.Random, pool: tuple[str, ...], n: int) -> list[str]:
    return rng.sample(pool, min(n, len(pool)))


def _title(rng: random.Random) -> str:
    adj = rng.choice(ADJECTIVES)
    sub = rng.choice(SUBSYSTEMS)
    topic = rng.choice(TOPICS)
    return f"{adj.capitalize()} {sub} {topic}"


def _paragraph(rng: random.Random, terms: list[str]) -> str:
    verb = rng.choice(VERBS)
    lead = rng.choice(TOPICS)
    return (
        f"This artifact concerns the {terms[0]} path and how the {terms[1]} "
        f"subsystem must {verb} {lead} without regressing {terms[2]}. "
        f"The {terms[0]} and {terms[2]} concerns are treated as first-class."
    )


# --- Per-type bodies ------------------------------------------------------
#
# Each builder returns the full Markdown for one artifact. Section skeletons
# mirror the real corpus so classification and validation pass; wording varies
# deterministically from the word bank so search has discriminating terms.


def _decision(index: int, rng: random.Random, terms: list[str],
              supersedes: str | None) -> str:
    body = [
        f"# ADR-{9000 + index} {_title(rng)} Decision",
        "",
        "## Status",
        "",
        "Accepted",
        "",
        "## Context",
        "",
        _paragraph(rng, terms),
        "",
        "## Decision",
        "",
        f"We standardise the {terms[0]} approach and require the "
        f"{terms[1]} to remain {rng.choice(ADJECTIVES)}.",
        "",
        "## Consequences",
        "",
        f"The {terms[2]} surface becomes easier to reason about; the "
        f"{terms[0]} path accepts a bounded cost in exchange.",
    ]
    if supersedes is not None:
        body += ["", "## Supersedes", "", f"- {supersedes}"]
    return "\n".join(body) + "\n"


def _requirement(index: int, rng: random.Random, terms: list[str],
                 related: list[str]) -> str:
    n_reqs = rng.randint(1, 3)
    statements = []
    for k in range(n_reqs):
        verb = rng.choice(VERBS).capitalize()
        obj = rng.choice(TOPICS)
        statements.append(
            f"- [REQ-{k + 1:03d}] The {terms[0]} subsystem SHALL {verb.lower()} "
            f"{obj} deterministically."
        )
    body = [
        f"# Requirement: {_title(rng)}",
        "",
        "## Status",
        "",
        "Accepted",
        "",
        "## Problem",
        "",
        f"The {terms[0]} path does not yet guarantee {terms[1]} at scale, so "
        f"{terms[2]} degrades as the corpus grows.",
        "",
        "## Requirements",
        "",
        *statements,
        "",
        "## Success Metrics",
        "",
        f"- {terms[0].capitalize()} stays flat as the corpus grows.",
        f"- {terms[1].capitalize()} is measured on every run.",
        "",
        "## Risks",
        "",
        f"- The {terms[2]} path could regress under load.",
    ]
    if related:
        body += ["", "## Related Decisions", ""]
        body += [f"- {r}" for r in related]
    return "\n".join(body) + "\n"


def _roadmap(index: int, rng: random.Random, terms: list[str],
             related: list[str]) -> str:
    body = [
        f"# {_title(rng)} Programme",
        "",
        "## Status",
        "",
        "Planned",
        "",
        "## Outcomes",
        "",
        f"Teams adopt the {terms[0]} surface without regressing {terms[1]}.",
        "",
        "## Initiatives",
        "",
        f"- Harden the {terms[1]} subsystem for {terms[0]}.",
        f"- Measure {terms[2]} across the corpus-size curve.",
        "",
        "## Success Measures",
        "",
        f"- {terms[0].capitalize()} remains bounded at the largest size.",
        "",
        "## Risks",
        "",
        f"- {terms[2].capitalize()} drifts as new artifacts land.",
        "",
        "## Related Decisions",
        "",
    ]
    body += [f"- {r}" for r in related]
    return "\n".join(body) + "\n"


def _prompt(index: int, rng: random.Random, terms: list[str]) -> str:
    verb = rng.choice(VERBS)
    body = [
        f"# {_title(rng)} Prompt",
        "",
        "## Status",
        "",
        "Active",
        "",
        "## Objective",
        "",
        f"Produce a {terms[0]} summary a fresh session can act on.",
        "",
        "## Input",
        "",
        f"The current {terms[1]} state and its {terms[2]} measurements.",
        "",
        "## Instructions",
        "",
        f"- Read the {terms[1]} state.",
        f"- {verb.capitalize()} the {terms[0]} findings.",
        "",
        "## Output",
        "",
        f"A short handoff covering {terms[0]} and {terms[2]}.",
    ]
    return "\n".join(body) + "\n"


def _design(index: int, rng: random.Random, terms: list[str]) -> str:
    body = [
        f"# {_title(rng)} Design",
        "",
        "## Status",
        "",
        "Proposed",
        "",
        "## Context",
        "",
        f"The {terms[0]} experience needs a clearer {terms[1]} surface.",
        "",
        "## User Need",
        "",
        f"An operator judging whether {terms[0]} stays flat as {terms[2]} grows.",
        "",
        "## Design",
        "",
        f"Surface {terms[1]} as a {rng.choice(ADJECTIVES)} panel beside the "
        f"{terms[0]} curve.",
        "",
        "## Constraints",
        "",
        f"- Must stay {rng.choice(ADJECTIVES)} and offline.",
        f"- Must not regress {terms[2]}.",
    ]
    return "\n".join(body) + "\n"


def _artifact_markdown(index: int, kind: str, seed: int,
                       dec_lo: int, dec_hi: int) -> str:
    rng = _rng(seed, index)
    terms = _words(rng, TOPICS, 3)
    front = ["---", "schema_version: 1", f"id: {artifact_id(index)}",
             f"type: {kind}", "---"]

    def pick_decisions(n: int, exclude: int | None = None) -> list[str]:
        span = dec_hi - dec_lo
        if span <= 0:
            return []
        chosen: list[int] = []
        attempts = 0
        while len(chosen) < min(n, span) and attempts < n * 8:
            attempts += 1
            d = dec_lo + rng.randrange(span)
            if d == exclude or d in chosen:
                continue
            chosen.append(d)
        return [artifact_id(d) for d in sorted(chosen)]

    if kind == "decision":
        # A superseding chain: every seventh decision retires the one before
        # it (a real, earlier decision id), giving relationships work to walk.
        supersedes = None
        if index > dec_lo and (index - dec_lo) % 7 == 0:
            supersedes = artifact_id(index - 1)
        body = _decision(index, rng, terms, supersedes)
    elif kind == "requirement":
        # ~60% of requirements carry 1-3 real decision references.
        related = pick_decisions(rng.randint(1, 3)) if rng.random() < 0.60 else []
        body = _requirement(index, rng, terms, related)
    elif kind == "roadmap":
        related = pick_decisions(rng.randint(1, 2)) or (
            [artifact_id(dec_lo)] if dec_hi > dec_lo else []
        )
        body = _roadmap(index, rng, terms, related)
    elif kind == "prompt":
        body = _prompt(index, rng, terms)
    elif kind == "design":
        body = _design(index, rng, terms)
    else:  # pragma: no cover - guarded by type_layout
        raise ValueError(kind)

    return "\n".join(front) + "\n" + body


def generate(count: int, out: Path, seed: int) -> list[tuple[str, int]]:
    """Write ``count`` artifacts under ``out``; return ``(relpath, size)`` list."""
    layout = type_layout(count)
    dec_lo, dec_hi = decision_range(layout)
    out.mkdir(parents=True, exist_ok=True)

    entries: list[tuple[str, int]] = []
    made_shards: set[str] = set()
    for index in range(count):
        kind = type_of(index, layout)
        shard = shard_dir(index)
        if shard not in made_shards:
            (out / shard).mkdir(parents=True, exist_ok=True)
            made_shards.add(shard)
        name = f"{TYPE_PREFIX[kind]}-{index:07d}.md"
        rel = f"{shard}/{name}"
        data = _artifact_markdown(index, kind, seed, dec_lo, dec_hi).encode("utf-8")
        with open(out / rel, "wb") as fh:
            fh.write(data)
        entries.append((rel, len(data)))
    return entries


def _per_type_counts(count: int) -> dict[str, int]:
    return {name: end - start for name, start, end in type_layout(count)}


def _manifest_sha(entries: list[tuple[str, int]]) -> str:
    h = hashlib.sha256()
    for rel, size in sorted(entries):
        h.update(f"{rel}\0{size}\n".encode("utf-8"))
    return h.hexdigest()


def write_manifest(out: Path, count: int, seed: int,
                   entries: list[tuple[str, int]]) -> Path:
    manifest = {
        "schema_version": 1,
        "count": count,
        "seed": seed,
        "files_per_shard": FILES_PER_SHARD,
        "per_type": _per_type_counts(count),
        "file_count": len(entries),
        "content_sha256": _manifest_sha(entries),
    }
    path = out / "manifest.json"
    # Compact, key-sorted, newline-terminated: byte-stable across runs.
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, required=True,
                        help="Number of artifacts to emit.")
    parser.add_argument("--out", type=Path, required=True,
                        help="Output directory (created if absent).")
    parser.add_argument("--seed", type=int, default=42,
                        help="Deterministic seed (default: 42).")
    parser.add_argument("--manifest", action="store_true",
                        help="Also write manifest.json (count, seed, per-type "
                             "counts, content sha256) for reproducibility.")
    args = parser.parse_args(argv)

    if args.count < 0:
        parser.error("--count must be non-negative")

    start = time.perf_counter()
    entries = generate(args.count, args.out, args.seed)
    elapsed = time.perf_counter() - start
    rate = len(entries) / elapsed if elapsed else float("inf")

    if args.manifest:
        write_manifest(args.out, args.count, args.seed, entries)

    counts = _per_type_counts(args.count)
    mix = ", ".join(f"{k}={v}" for k, v in counts.items())
    print(
        f"generated {len(entries)} artifacts into {args.out} "
        f"in {elapsed:.2f}s ({rate:,.0f} files/s)"
    )
    print(f"  mix: {mix}")
    if args.manifest:
        print(f"  manifest: {args.out / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
