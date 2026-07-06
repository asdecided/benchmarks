# SPDX-License-Identifier: Apache-2.0
"""The deterministic seeded edit engine for the durability member.

A taxonomy of *logical* edits over the granularity member's dual renderings,
applied identically to both — the per-file artifact and the corresponding canon
``##`` block for the same decision. Every edit is a pure function of
``(seed, round, seq)``: the same call re-derives the same edit stream, so a run
is byte-reproducible and every rate/condition sees the identical proposals (the
gate, not the proposals, is what differs between conditions).

Two families:

- **clean edits** — the realistic churn a corpus takes: ``reword-context``,
  ``append-consequence``, ``supersede`` (retire a live decision with a new,
  correctly-linked successor), ``add-cross-reference``. These keep both
  renderings valid; a clean supersede even *improves* safety (one more
  correctly-retired decision).

- **break classes** — the sloppy forms a real review lets slip. A parameterised
  fraction ``p`` of edits land ONE break instead of the clean form:

  - ``malformed-status``  — a superseded decision's status text is mangled
    (``Superseded`` → ``superceded`` / ``SUPERSEDED (see v2)`` /
    ``Status : Superseded``). In canon the streaming live-filter no longer
    recognises it and the retired block ranks live (a leak); in the artifacts
    the value is not a valid decision status, so the engine drops the record
    (no leak) and ``rac validate`` flags ``invalid-decision-status``.
  - ``heading-slip``      — the status heading loses a level (canon
    ``### Status`` → ``#### Status``; artifact ``## Status`` → ``### Status``).
    Canon's status filter keys on the exact ``### Status`` heading, so the
    retired block ranks live (a leak); the engine's parser is level-tolerant,
    so the artifact is unaffected.
  - ``boundary-break``    — a block boundary is destroyed at the target. In
    canon the target's ``## `` heading is stripped, so it merges into its
    predecessor: the target's id becomes unreachable and the predecessor chunk
    is contaminated with foreign text (blast radius > 1). The structural analog
    in the artifacts is frontmatter identity damage (``id:`` → ``id``) that
    drops the *same* target from the index (blast radius exactly 1).
  - ``duplicate-id``      — the supersede reuses an EXISTING id (canon: a block
    heading id repeated; artifacts: a new file whose frontmatter id duplicates
    a live one).
  - ``dangling-ref``      — the supersede's ``Supersedes`` line targets an id
    that does not exist anywhere.

Which decision each break touches is chosen to be *consequential*: the
leak-bearing breaks (``malformed-status`` / ``heading-slip``) land on the
superseded ancestors the query set actually exercises, and ``boundary-break``
lands on a live head the query set expects back — so the decay curve measures
breakage that reaches a reader, not breakage in corpus regions no query touches.
That targeting is a recorded assumption (``TAXONOMY_VERSION``), stated here for
critique, not tuned to flatter either rendering.

Edits mutate copies under a working directory; the source corpus is never
touched. Nothing here imports the engine (DG-ADR-0001); stdlib only.
"""

from __future__ import annotations

import random
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "granularity"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scale"))

from _common import shard_dir  # noqa: E402  (scale sibling: shard layout)
from _model import artifact_id  # noqa: E402  (granularity sibling: GRA-tagged ids)

# The taxonomy and its targeting rules are a recorded assumption; bump this when
# either changes so a mixed run is never aggregated as one.
TAXONOMY_VERSION = 1

CLEAN_KINDS = (
    "reword-context",
    "append-consequence",
    "supersede",
    "add-cross-reference",
)
BREAK_CLASSES = (
    "malformed-status",
    "heading-slip",
    "boundary-break",
    "duplicate-id",
    "dangling-ref",
)

# The malformed-status forms a sloppy edit picks from (all non-canonical, so the
# canon filter misses them and the engine rejects them as an invalid status).
MALFORMED_STATUS = ("superceded", "SUPERSEDED (see v2)", "Status : Superseded")


def _rng(*key: object) -> random.Random:
    """A stream keyed only on ``key`` — independent of PYTHONHASHSEED."""
    return random.Random(":".join(str(k) for k in key))


@dataclass(frozen=True)
class Edit:
    """One logical edit, renderable into either variant.

    ``op`` is a clean kind or a break class. ``target`` is the decision index
    the edit damages/rewrites. Supersede-family ops (clean supersede,
    ``duplicate-id``, ``dangling-ref``) also carry ``new_index`` (the successor
    the edit introduces) and, where relevant, ``dup_of`` / ``dangling_id``.
    """

    round: int
    seq: int
    sloppy: bool
    op: str
    target: int
    new_index: int | None = None
    dup_of: int | None = None
    dangling_id: str | None = None
    # The decision indices this edit is *responsible* for — the ids a gate would
    # attribute to it. Used to decide whether a gate finding rejects this edit.
    responsible: tuple[int, ...] = field(default_factory=tuple)


# --- planning -------------------------------------------------------------


@dataclass(frozen=True)
class Pools:
    """The decision-index pools the planner targets, derived from the query set.

    ``superseded`` — query-exercised superseded ancestors (leak targets).
    ``heads``      — query-exercised live heads (miss targets).
    ``neutral``    — live decisions no query touches (clean-churn targets, so a
                     clean edit never rewrites a query's own ground truth).
    ``count``      — corpus size, so new successor indices never collide.
    """

    superseded: tuple[int, ...]
    heads: tuple[int, ...]
    neutral: tuple[int, ...]
    count: int


def _pick(pool: tuple[int, ...], rng: random.Random) -> int:
    return pool[rng.randrange(len(pool))] if pool else 0


def plan(
    seed: int, rounds: int, edits_per_round: int, p: float, pools: Pools
) -> list[list[Edit]]:
    """The full edit programme: ``rounds`` lists of ``edits_per_round`` edits.

    Pure function of ``(seed, rounds, edits_per_round, p, pools)``. ``p`` is the
    sloppy fraction; a sloppy edit lands one break class (uniform over the five),
    a clean edit one of the four kinds (uniform).
    """
    programme: list[list[Edit]] = []
    for r in range(rounds):
        round_edits: list[Edit] = []
        for seq in range(edits_per_round):
            rng = _rng(seed, "edit", r, seq)
            new_index = pools.count + r * edits_per_round + seq
            if rng.random() < p:
                round_edits.append(_break_edit(rng, r, seq, new_index, pools))
            else:
                round_edits.append(_clean_edit(rng, r, seq, new_index, pools))
        programme.append(round_edits)
    return programme


def _clean_edit(
    rng: random.Random, r: int, seq: int, new_index: int, pools: Pools
) -> Edit:
    op = CLEAN_KINDS[rng.randrange(len(CLEAN_KINDS))]
    # Clean edits are realistic churn on decisions no query touches, so a valid
    # supersede (which flips a decision to Superseded) never rewrites a query's
    # own ground truth — clean edits stay metric-neutral in every condition.
    target = _pick(pools.neutral, rng)
    if op == "supersede":
        return Edit(
            r,
            seq,
            False,
            op,
            target,
            new_index=new_index,
            responsible=(target, new_index),
        )
    return Edit(r, seq, False, op, target, responsible=(target,))


def _break_edit(
    rng: random.Random, r: int, seq: int, new_index: int, pools: Pools
) -> Edit:
    cls = BREAK_CLASSES[rng.randrange(len(BREAK_CLASSES))]
    if cls in ("malformed-status", "heading-slip"):
        target = _pick(pools.superseded, rng)  # leak target
        return Edit(r, seq, True, cls, target, responsible=(target,))
    if cls == "boundary-break":
        target = _pick(pools.heads, rng)  # miss target
        return Edit(r, seq, True, cls, target, responsible=(target,))
    if cls == "duplicate-id":
        target = _pick(pools.heads, rng)
        dup_of = _pick(pools.heads, rng)
        # ``dup_of`` is what the canon linter flags (the id it sees twice); the
        # artifact gate flags ``new_index`` (the new file). Both are responsible.
        return Edit(
            r,
            seq,
            True,
            cls,
            target,
            new_index=new_index,
            dup_of=dup_of,
            responsible=(target, new_index, dup_of),
        )
    # dangling-ref
    target = _pick(pools.heads, rng)
    dangling = artifact_id(pools.count * 10 + r * 1000 + seq)  # guaranteed absent
    return Edit(
        r,
        seq,
        True,
        cls,
        target,
        new_index=new_index,
        dangling_id=dangling,
        responsible=(target, new_index),
    )


# --- shared body text -----------------------------------------------------


def _reworded_context(edit: Edit) -> str:
    rng = _rng("reword", edit.round, edit.seq, edit.target)
    tag = rng.randrange(100000)
    return (
        f"Revised in review pass {edit.round}: the approach is restated for "
        f"clarity without changing intent (edit token {tag})."
    )


def _appended_consequence(edit: Edit) -> str:
    return (
        f"Follow-up noted in round {edit.round}: the bounded cost is accepted "
        f"and tracked (edit {edit.seq})."
    )


def _cross_reference(edit: Edit, pools: Pools) -> str:
    rng = _rng("xref", edit.round, edit.seq, edit.target)
    other = _pick(pools.heads, rng)
    return f"- See also {artifact_id(other)}"


# --- canon rendering (text transforms anchored by block id) ---------------

_CANON_NEXT = re.compile(r"\n## ")


def _canon_span(text: str, dec_id: str) -> tuple[int, int] | None:
    """``(start, end)`` of the ``## <dec_id> — …`` block, or None if absent."""
    head = f"## {dec_id} "
    start = text.find("\n" + head)
    if start >= 0:
        start += 1
    elif text.startswith(head):
        start = 0
    else:
        return None
    m = _CANON_NEXT.search(text, start + len(head))
    end = m.start() + 1 if m else len(text)
    return start, end


def _canon_edit_block(text: str, dec_id: str, transform) -> str:
    span = _canon_span(text, dec_id)
    if span is None:
        return text  # target already removed by an earlier edit — no-op
    start, end = span
    return text[:start] + transform(text[start:end]) + text[end:]


def _canon_block(dec_id: str, title: str, status: str, supersedes: str | None) -> str:
    lines = [
        f"## {dec_id} — {title}",
        "",
        "### Status",
        "",
        status,
        "",
        "### Context",
        "",
        f"A successor introduced by the durability edit engine for {dec_id}.",
        "",
        "### Decision",
        "",
        "We adopt the revised approach.",
        "",
        "### Consequences",
        "",
        "The prior decision is retired.",
    ]
    if supersedes is not None:
        lines += ["", "### Supersedes", "", f"- {supersedes}"]
    return "\n".join(lines) + "\n"


def apply_canon(text: str, edit: Edit, pools: Pools) -> str:
    """Return ``text`` with ``edit`` applied to the decisions-canon rendering."""
    dec_id = artifact_id(edit.target)
    op = edit.op

    if op == "reword-context":
        new = _reworded_context(edit)
        return _canon_edit_block(
            text,
            dec_id,
            lambda b: _replace_section_body(b, "### Context", new),
        )
    if op == "append-consequence":
        line = _appended_consequence(edit)
        return _canon_edit_block(
            text,
            dec_id,
            lambda b: _append_section_line(b, "### Consequences", line),
        )
    if op == "add-cross-reference":
        line = _cross_reference(edit, pools)
        return _canon_edit_block(text, dec_id, lambda b: _append_block_line(b, line))
    if op == "supersede":
        text = _canon_edit_block(text, dec_id, lambda b: _set_status(b, "Superseded"))
        block = _canon_block(
            artifact_id(edit.new_index), "Durability successor", "Accepted", dec_id
        )
        return _canon_append(text, dec_id, block)
    if op == "malformed-status":
        variant = MALFORMED_STATUS[
            _rng("mal", edit.round, edit.seq).randrange(len(MALFORMED_STATUS))
        ]
        return _canon_edit_block(text, dec_id, lambda b: _set_status(b, variant))
    if op == "heading-slip":
        return _canon_edit_block(
            text, dec_id, lambda b: b.replace("### Status", "#### Status", 1)
        )
    if op == "boundary-break":
        return _canon_edit_block(
            text, dec_id, lambda b: b.replace(f"## {dec_id} ", f"{dec_id} ", 1)
        )
    if op == "duplicate-id":
        block = _canon_block(
            artifact_id(edit.dup_of), "Duplicate-id successor", "Accepted", dec_id
        )
        return _canon_append(text, dec_id, block)
    if op == "dangling-ref":
        block = _canon_block(
            artifact_id(edit.new_index),
            "Dangling successor",
            "Accepted",
            edit.dangling_id,
        )
        return _canon_append(text, dec_id, block)
    raise ValueError(op)


def _canon_append(text: str, after_id: str, block: str) -> str:
    """Insert ``block`` immediately after ``after_id``'s block, else at EOF."""
    span = _canon_span(text, after_id)
    if span is None:
        return text.rstrip("\n") + "\n\n" + block
    _start, end = span
    return text[:end] + "\n" + block + text[end:]


# --- artifact rendering (file transforms) ---------------------------------


def _artifact_file(art_dir: Path, index: int) -> Path | None:
    """The base decision file for ``index`` (named ``dec-<index>.md``)."""
    p = art_dir / shard_dir(index) / f"dec-{index:07d}.md"
    return p if p.is_file() else None


def _new_artifact(
    art_dir: Path, index: int, front_id: str, title: str, supersedes: str | None
) -> Path:
    shard = art_dir / shard_dir(index)
    shard.mkdir(parents=True, exist_ok=True)
    lines = [
        "---",
        "schema_version: 1",
        f"id: {front_id}",
        "type: decision",
        "---",
        f"# {title}",
        "",
        "## Status",
        "",
        "Accepted",
        "",
        "## Context",
        "",
        f"A successor introduced by the durability edit engine ({front_id}).",
        "",
        "## Decision",
        "",
        "We adopt the revised approach.",
        "",
        "## Consequences",
        "",
        "The prior decision is retired.",
    ]
    if supersedes is not None:
        lines += ["", "## Supersedes", "", f"- {supersedes}"]
    path = shard / f"sup-{index:07d}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def apply_artifacts(art_dir: Path, edit: Edit, pools: Pools) -> None:
    """Apply ``edit`` to the per-file artifact rendering under ``art_dir``."""
    op = edit.op
    target = _artifact_file(art_dir, edit.target)

    if op == "reword-context":
        if target:
            _rewrite(
                target,
                lambda t: _replace_section_body(
                    t, "## Context", _reworded_context(edit)
                ),
            )
        return
    if op == "append-consequence":
        if target:
            _rewrite(
                target,
                lambda t: _append_section_line(
                    t, "## Consequences", _appended_consequence(edit)
                ),
            )
        return
    if op == "add-cross-reference":
        if target:
            _rewrite(
                target, lambda t: _append_block_line(t, _cross_reference(edit, pools))
            )
        return
    if op == "supersede":
        if target:
            _rewrite(target, lambda t: _set_status(t, "Superseded"))
        _new_artifact(
            art_dir,
            edit.new_index,
            artifact_id(edit.new_index),
            "Durability successor",
            artifact_id(edit.target),
        )
        return
    if op == "malformed-status":
        if target:
            variant = MALFORMED_STATUS[
                _rng("mal", edit.round, edit.seq).randrange(len(MALFORMED_STATUS))
            ]
            _rewrite(target, lambda t: _set_status(t, variant))
        return
    if op == "heading-slip":
        if target:
            _rewrite(target, lambda t: t.replace("## Status", "### Status", 1))
        return
    if op == "boundary-break":
        if target:
            # Frontmatter identity damage: 'id:' -> 'id' drops the file from the index.
            _rewrite(target, lambda t: t.replace("\nid: ", "\nid ", 1))
        return
    if op == "duplicate-id":
        _new_artifact(
            art_dir,
            edit.new_index,
            artifact_id(edit.dup_of),
            "Duplicate-id successor",
            artifact_id(edit.target),
        )
        return
    if op == "dangling-ref":
        _new_artifact(
            art_dir,
            edit.new_index,
            artifact_id(edit.new_index),
            "Dangling successor",
            edit.dangling_id,
        )
        return
    raise ValueError(op)


# --- section helpers (shared by both renderings) --------------------------


def _rewrite(path: Path, transform) -> None:
    path.write_text(transform(path.read_text(encoding="utf-8")), encoding="utf-8")


def _set_status(text: str, value: str) -> str:
    """Replace the first status body line (after a ``Status`` heading)."""
    m = re.search(r"(#+ Status\s*\n\s*\n)([^\n]*)", text)
    if not m:
        return text
    return text[: m.start(2)] + value + text[m.end(2) :]


def _replace_section_body(text: str, heading: str, new_body: str) -> str:
    """Replace the first body line under ``heading`` (exact heading match)."""
    idx = text.find(heading + "\n")
    if idx < 0:
        return text
    body = text.find("\n\n", idx)
    if body < 0:
        return text
    body += 2
    end = text.find("\n", body)
    if end < 0:
        end = len(text)
    return text[:body] + new_body + text[end:]


def _append_section_line(text: str, heading: str, line: str) -> str:
    """Append ``line`` to the body under ``heading`` (before the next heading).

    When ``heading`` is the block's last section, the line is inserted *before*
    the block's trailing newlines so the block boundary (the blank line before
    the next ``## `` heading) is preserved — otherwise the appended line would
    butt against the next block and silently merge the two chunks.
    """
    idx = text.find(heading + "\n")
    if idx < 0:
        return text
    nxt = text.find("\n## ", idx + len(heading))
    if nxt < 0:
        nxt = text.find("\n### ", idx + len(heading))
    insert = nxt if nxt >= 0 else len(text.rstrip("\n"))
    return text[:insert] + "\n" + line + text[insert:]


def _append_block_line(text: str, line: str) -> str:
    """Append ``line`` at the block/file end, preserving the trailing newlines."""
    insert = len(text.rstrip("\n"))
    return text[:insert] + "\n\n" + line + text[insert:]
