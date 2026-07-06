#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Emit the granularity corpus in both renderings from one source of truth.

    python granularity/build_corpus.py --count N --out DIR [--seed 42] [--manifest]

From the deterministic records in ``_model`` this writes, into ``DIR``:

  artifacts/  one valid RAC artifact per file (~70% decisions, ~30%
              requirements), sharded at 2000 files/dir. Superseded decisions
              carry a ``Superseded`` status the engine's live filter reads;
              superseding decisions carry a real ``Supersedes`` edge, so
              ``rac relationships --validate`` resolves the chains.
  canon/      decisions-canon.md and requirements-canon.md — the SAME content,
              one ``## <id> — <title>`` block per artifact, its sections nested
              as H3 (including the status line and any supersedes line as
              text). Written by streaming: one artifact's block is rendered,
              flushed, and dropped before the next, so no whole canon is ever
              held in memory (a 100k canon is hundreds of MB).

Output is byte-identical for identical ``(count, seed)``. This is generator
tooling for an evidence run, not an engine consumer: it never imports ``rac``
(DG-ADR-0001). ``--manifest`` records count, seed, and a per-variant sha256;
the builder self-check runs ``rac validate`` and ``rac relationships
--validate`` over the artifacts variant as an external CLI.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _model import (  # noqa: E402  (local module, path-injected above)
    MODEL_VERSION,
    Decision,
    Requirement,
    decision_count,
    decision_record,
    decision_sections,
    requirement_record,
    requirement_sections,
    type_of,
)
from _common import shard_dir  # noqa: E402  (scale sibling, on path via _model)

_FRONT_TYPE = {"decision": "decision", "requirement": "requirement"}


# --- rendering (both variants derive from the same section lists) ---------


def _record(index: int, seed: int, n_decisions: int) -> Decision | Requirement:
    if type_of(index, n_decisions) == "decision":
        return decision_record(index, seed, n_decisions)
    return requirement_record(index, seed, n_decisions)


def _sections(record: Decision | Requirement) -> list[tuple[str, list[str]]]:
    if isinstance(record, Decision):
        return decision_sections(record)
    return requirement_sections(record)


def render_artifact(record: Decision | Requirement, kind: str) -> str:
    """One valid per-file RAC artifact: frontmatter + H2 sections."""
    lines = [
        "---",
        "schema_version: 1",
        f"id: {record.id}",
        f"type: {_FRONT_TYPE[kind]}",
        "---",
        f"# {record.title}",
    ]
    for title, body in _sections(record):
        lines += ["", f"## {title}", "", *body]
    return "\n".join(lines) + "\n"


def render_canon_block(record: Decision | Requirement) -> str:
    """One canon block: an ``## <id> — <title>`` heading, sections nested as H3.

    Same content as the per-file artifact, minus the frontmatter — the id rides
    in the heading and the status / supersedes lines are plain text under it, so
    a heading-structure chunker (the strongest simple treatment a monolithic
    document supports) recovers exactly one artifact's block per ``##``.
    """
    lines = [f"## {record.id} — {record.title}"]
    for title, body in _sections(record):
        lines += ["", f"### {title}", "", *body]
    return "\n".join(lines) + "\n"


# --- streaming writers ----------------------------------------------------


def _canon_header(kind_plural: str) -> str:
    return (
        f"# {kind_plural} canon\n\n"
        "One monolithic document holding one heading block per "
        f"{kind_plural.lower().rstrip('s')}. Not a RAC artifact: the engine's "
        "file cap, single frontmatter identity, and duplicate-section collapse "
        "all refuse it (ADR-010). Chunk it by heading to search it.\n"
    )


def build(count: int, out: Path, seed: int) -> dict[str, object]:
    """Stream both renderings; return manifest data (counts + per-variant sha)."""
    n_decisions = decision_count(count)
    artifacts = out / "artifacts"
    canon = out / "canon"
    artifacts.mkdir(parents=True, exist_ok=True)
    canon.mkdir(parents=True, exist_ok=True)

    art_hash = hashlib.sha256()
    dec_canon_hash = hashlib.sha256()
    req_canon_hash = hashlib.sha256()
    made_shards: set[str] = set()
    n_dec = n_req = 0

    dec_path = canon / "decisions-canon.md"
    req_path = canon / "requirements-canon.md"
    with (
        open(dec_path, "w", encoding="utf-8") as dec_fh,
        open(req_path, "w", encoding="utf-8") as req_fh,
    ):
        dec_header = _canon_header("Decisions")
        req_header = _canon_header("Requirements")
        dec_fh.write(dec_header)
        req_fh.write(req_header)
        dec_canon_hash.update(dec_header.encode("utf-8"))
        req_canon_hash.update(req_header.encode("utf-8"))

        for index in range(count):
            kind = type_of(index, n_decisions)
            record = _record(index, seed, n_decisions)

            # Per-file artifact variant.
            shard = shard_dir(index)
            if shard not in made_shards:
                (artifacts / shard).mkdir(parents=True, exist_ok=True)
                made_shards.add(shard)
            prefix = "dec" if kind == "decision" else "req"
            rel = f"{shard}/{prefix}-{index:07d}.md"
            data = render_artifact(record, kind).encode("utf-8")
            with open(artifacts / rel, "wb") as fh:
                fh.write(data)
            art_hash.update(f"{rel}\0".encode("utf-8"))
            art_hash.update(data)

            # Canon variant (streamed: one block rendered, written, dropped).
            block = render_canon_block(record).encode("utf-8")
            if kind == "decision":
                dec_fh.write("\n")
                dec_fh.write(block.decode("utf-8"))
                dec_canon_hash.update(b"\n")
                dec_canon_hash.update(block)
                n_dec += 1
            else:
                req_fh.write("\n")
                req_fh.write(block.decode("utf-8"))
                req_canon_hash.update(b"\n")
                req_canon_hash.update(block)
                n_req += 1

    return {
        "schema_version": 1,
        "model_version": MODEL_VERSION,
        "count": count,
        "seed": seed,
        "per_type": {"decision": n_dec, "requirement": n_req},
        "sha256": {
            "artifacts": art_hash.hexdigest(),
            "decisions_canon": dec_canon_hash.hexdigest(),
            "requirements_canon": req_canon_hash.hexdigest(),
        },
    }


def write_manifest(out: Path, manifest: dict[str, object]) -> Path:
    path = out / "manifest.json"
    path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return path


# --- builder self-check (rac as an external CLI) --------------------------


def _self_check(artifacts: Path) -> None:
    """Assert the per-file variant passes validate + relationship checks."""
    for args in (
        ["rac", "validate", str(artifacts)],
        ["rac", "relationships", str(artifacts), "--validate"],
    ):
        proc = subprocess.run(args, capture_output=True, text=True, check=False)
        assert proc.returncode == 0, (
            f"self-check failed: {' '.join(args)} exited {proc.returncode}\n"
            f"{proc.stdout}\n{proc.stderr}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--count",
        type=int,
        required=True,
        help="Number of artifacts to emit (both renderings).",
    )
    parser.add_argument(
        "--out", type=Path, required=True, help="Output directory (created if absent)."
    )
    parser.add_argument(
        "--seed", type=int, default=42, help="Deterministic seed (default: 42)."
    )
    parser.add_argument(
        "--manifest",
        action="store_true",
        help="Also write manifest.json (count, seed, per-variant sha256).",
    )
    parser.add_argument(
        "--no-self-check",
        action="store_true",
        help="Skip the rac validate / relationships self-check "
        "(the self-check needs rac on PATH).",
    )
    args = parser.parse_args(argv)
    if args.count < 0:
        parser.error("--count must be non-negative")

    start = time.perf_counter()
    manifest = build(args.count, args.out, args.seed)
    elapsed = time.perf_counter() - start

    if args.manifest:
        write_manifest(args.out, manifest)

    if not args.no_self_check:
        _self_check(args.out / "artifacts")

    per_type = manifest["per_type"]
    print(
        f"built {args.count} artifacts into {args.out} in {elapsed:.2f}s "
        f"(decisions={per_type['decision']}, requirements={per_type['requirement']})"
    )
    print(f"  artifacts sha256: {manifest['sha256']['artifacts']}")
    print(
        f"  canon sha256: decisions={manifest['sha256']['decisions_canon'][:12]}… "
        f"requirements={manifest['sha256']['requirements_canon'][:12]}…"
    )
    if args.manifest:
        print(f"  manifest: {args.out / 'manifest.json'}")
    if not args.no_self_check:
        print("  self-check: rac validate + relationships --validate OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
