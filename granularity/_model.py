# SPDX-License-Identifier: Apache-2.0
"""The single deterministic source of truth for the granularity member.

One corpus, two renderings. Every artifact record here is a pure function of
``(seed, index)``, so the per-file variant, the monolithic canon variant, and
the query set are all derived from the *same* structure without any shared
state on disk. The corpus builder streams both renderings from these records;
the query builder and the canon-arm scorer re-derive the identical structure to
know which decision is live and which are superseded ancestors.

Granularity is the only thing that differs between the two renderings: the
per-file variant is one valid RAC artifact per file (typed identity, a
``Superseded`` status the engine's live filter reads, real supersession
edges); the canon variant is the same content concatenated into two documents,
one ``##`` block per artifact. ADR-010 says a document is not an artifact — the
engine's file cap, single frontmatter identity, and duplicate-section collapse
all refuse a canon file — so the canon arm is what a team actually does with a
monolithic document: chunk it by heading and search the chunks.

Vocabulary and the id/shard idioms are reused from the scale member's
``_common`` so the two evidence corpora read the same way; nothing here imports
the engine (DG-ADR-0001). Stdlib only.
"""

from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from pathlib import Path

# Reuse the scale member's engine-free vocabulary and shard idioms (the task's
# instruction: import from scale/_common.py the way scale's own modules do).
_SCALE_DIR = Path(__file__).resolve().parents[1] / "scale"
sys.path.insert(0, str(_SCALE_DIR))

from _common import (  # noqa: E402  (path-injected sibling module)
    ADJECTIVES,
    SUBSYSTEMS,
    TOPICS,
    VERBS,
    _ALPHABET,
)

# The granularity corpus fixes the repository key at RAC and reserves a "GRA"
# lead in the 12-char suffix so its ids never collide with the scale "SCA"
# corpus, leaving nine base32 digits of counter.
ID_KEY = "RAC"
_ID_TAG = "GRA"
_COUNTER_WIDTH = 9

# ~70% decisions / ~30% requirements. Decisions come first in id order so a
# requirement can reference a decision id guaranteed to already exist.
DECISION_SHARE = 0.70

# Positional supersession layout, keyed on the decision ordinal ``j`` (index
# within the decision range). Each block of BLOCK decisions carries two chains
# and a run of standalone live decisions:
#   positions 0,1,2 -> chain "A" (length 3): 0 and 1 superseded, 2 is the head
#   positions 3,4   -> chain "B" (length 2): 3 superseded, 4 is the head
#   positions 5..   -> standalone live decisions
# That makes 3 of every 20 decisions superseded (~15%, the roadmap's figure)
# and 5 of every 20 chain members (~25% participate in a chain).
BLOCK = 20
_CHAINS = {"A": (0, 1, 2), "B": (3, 4)}


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
    """The deterministic canonical id for the artifact at ``index``."""
    return f"{ID_KEY}-{_ID_TAG}{_encode(index, _COUNTER_WIDTH)}"


def _rng(*key: object) -> random.Random:
    """A stream keyed only on ``key`` — independent of PYTHONHASHSEED."""
    return random.Random(":".join(str(k) for k in key))


# --- corpus layout --------------------------------------------------------


def decision_count(count: int) -> int:
    """How many of ``count`` artifacts are decisions (the rest requirements)."""
    if count < 0:
        raise ValueError("count must be non-negative")
    return round(count * DECISION_SHARE)


def type_of(index: int, n_decisions: int) -> str:
    return "decision" if index < n_decisions else "requirement"


# --- supersession chains --------------------------------------------------


@dataclass(frozen=True)
class ChainInfo:
    """Where decision ``index`` sits in the positional supersession layout."""

    group: str | None  # "A" / "B" / None (standalone)
    key: str  # stable per-chain key for shared vocabulary
    members: tuple[int, ...]  # existing member indices, low->high (superseded->head)
    head: int  # the live head index (highest existing member)
    superseded: bool  # is this index superseded?
    supersedes: int | None  # the immediate existing predecessor, if any


def chain_info(index: int, n_decisions: int) -> ChainInfo:
    """The chain membership of decision ``index`` — a pure positional function.

    A chain member only supersedes / is superseded by members that actually
    exist (a corpus can end mid-block); the live head is the highest-position
    member present, so a truncated chain still resolves to exactly one live
    decision.
    """
    j = index
    blk, pos = divmod(j, BLOCK)
    group = next((g for g, positions in _CHAINS.items() if pos in positions), None)
    if group is None:
        return ChainInfo("standalone", f"solo:{index}", (index,), index, False, None)

    positions = _CHAINS[group]
    members = [blk * BLOCK + p for p in positions if blk * BLOCK + p < n_decisions]
    head = max(members)
    lower = [m for m in members if m < index]
    return ChainInfo(
        group=group,
        key=f"chain:{blk}:{group}",
        members=tuple(members),
        head=head,
        superseded=index != head,
        supersedes=(max(lower) if lower else None),
    )


def _terms(seed: int, key: str, n: int = 3) -> list[str]:
    """``n`` distinct topic terms for a chain key or a standalone artifact.

    Chain members share one key, so they share these terms — that is what makes
    a supersession query collide the superseded ancestor with its live head.
    """
    return _rng(seed, key).sample(TOPICS, n)


# --- artifact records -----------------------------------------------------


@dataclass(frozen=True)
class Decision:
    index: int
    id: str
    title: str
    status: str  # "Accepted" | "Superseded"
    terms: tuple[str, ...]
    supersedes: str | None
    chain_key: str
    head_id: str
    ancestor_ids: tuple[str, ...]  # superseded members of this decision's chain


@dataclass(frozen=True)
class Requirement:
    index: int
    id: str
    title: str
    terms: tuple[str, ...]
    related: tuple[str, ...]  # referenced decision ids (live)
    # If this requirement references a live chain head, the head and its
    # superseded ancestors — the raw material of a "related" query case.
    head_ref: str | None = None
    head_ancestors: tuple[str, ...] = field(default_factory=tuple)


def _title(seed: int, index: int, topic: str) -> str:
    rng = _rng(seed, "title", index)
    return f"{rng.choice(ADJECTIVES).capitalize()} {rng.choice(SUBSYSTEMS)} {topic}"


def decision_record(index: int, seed: int, n_decisions: int) -> Decision:
    info = chain_info(index, n_decisions)
    terms = _terms(seed, info.key)
    status = "Superseded" if info.superseded else "Accepted"
    supersedes = artifact_id(info.supersedes) if info.supersedes is not None else None
    ancestors = tuple(artifact_id(m) for m in info.members if m != info.head)
    return Decision(
        index=index,
        id=artifact_id(index),
        title=_title(seed, index, terms[0]),
        status=status,
        terms=tuple(terms),
        supersedes=supersedes,
        chain_key=info.key,
        head_id=artifact_id(info.head),
        ancestor_ids=ancestors,
    )


def _pick_related(index: int, seed: int, n_decisions: int) -> list[int]:
    """1-3 live decision indices this requirement references.

    References target live decisions only (chain heads or standalone lives), so
    the per-file variant's ``rac relationships --validate`` resolves every edge
    to a present decision and no reference points at a superseded record.
    """
    rng = _rng(seed, "related", index)
    if n_decisions <= 0:
        return []
    chosen: list[int] = []
    for _ in range(rng.randint(1, 3)):
        cand = rng.randrange(n_decisions)
        head = chain_info(cand, n_decisions).head
        if head not in chosen:
            chosen.append(head)
    return sorted(chosen)


def requirement_record(index: int, seed: int, n_decisions: int) -> Requirement:
    terms = _terms(seed, f"req:{index}")
    related_idx = _pick_related(index, seed, n_decisions)
    related = tuple(artifact_id(i) for i in related_idx)

    head_ref: str | None = None
    head_ancestors: tuple[str, ...] = ()
    for i in related_idx:
        info = chain_info(i, n_decisions)
        anc = tuple(artifact_id(m) for m in info.members if m != info.head)
        if anc:  # this reference is a live chain head with superseded ancestors
            head_ref = artifact_id(info.head)
            head_ancestors = anc
            # Fold the head's shared chain terms into the requirement's own
            # vocabulary so a "related" query drawn from the requirement
            # collides the head with its ancestors in the canon rendering.
            terms = tuple(_terms(seed, info.key))
            break

    return Requirement(
        index=index,
        id=artifact_id(index),
        title=_title(seed, index, terms[0]),
        terms=terms,
        related=related,
        head_ref=head_ref,
        head_ancestors=head_ancestors,
    )


# --- shared body prose (identical text in both renderings) ----------------


def _context(terms: tuple[str, ...]) -> str:
    return (
        f"This artifact concerns the {terms[0]} path and how the {terms[1]} "
        f"subsystem must sustain {terms[2]} without regressing {terms[0]}. The "
        f"{terms[0]} and {terms[2]} concerns are treated as first-class."
    )


def decision_sections(dec: Decision) -> list[tuple[str, list[str]]]:
    """(section title, body lines) pairs — the shared decision content.

    Both renderings emit exactly these sections in this order; only the heading
    level differs (H2 in the per-file artifact, H3 nested under the canon
    block). A ``Supersedes`` section is present only on a superseding decision.
    """
    rng = _rng("dec-body", dec.index)
    sections: list[tuple[str, list[str]]] = [
        ("Status", [dec.status]),
        ("Context", [_context(dec.terms)]),
        (
            "Decision",
            [
                f"We standardise the {dec.terms[0]} approach and require the "
                f"{dec.terms[1]} to remain {rng.choice(ADJECTIVES)}."
            ],
        ),
        (
            "Consequences",
            [
                f"The {dec.terms[2]} surface becomes easier to reason about; the "
                f"{dec.terms[0]} path accepts a bounded cost in exchange."
            ],
        ),
    ]
    if dec.supersedes is not None:
        sections.append(("Supersedes", [f"- {dec.supersedes}"]))
    return sections


def requirement_sections(req: Requirement) -> list[tuple[str, list[str]]]:
    """(section title, body lines) pairs — the shared requirement content."""
    rng = _rng("req-body", req.index)
    statements = []
    for k in range(rng.randint(1, 3)):
        verb = rng.choice(VERBS)
        statements.append(
            f"- [REQ-{k + 1:03d}] The {req.terms[0]} subsystem SHALL {verb} "
            f"{req.terms[k % len(req.terms)]} deterministically."
        )
    sections: list[tuple[str, list[str]]] = [
        ("Status", ["Accepted"]),
        (
            "Problem",
            [
                f"The {req.terms[0]} path does not yet guarantee {req.terms[1]} at "
                f"scale, so {req.terms[2]} degrades as the corpus grows."
            ],
        ),
        ("Requirements", statements),
        (
            "Success Metrics",
            [
                f"- {req.terms[0].capitalize()} stays flat as the corpus grows.",
                f"- {req.terms[1].capitalize()} is measured on every run.",
            ],
        ),
        ("Risks", [f"- The {req.terms[2]} path could regress under load."]),
    ]
    if req.related:
        sections.append(("Related Decisions", [f"- {r}" for r in req.related]))
    return sections
