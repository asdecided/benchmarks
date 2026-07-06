# SPDX-License-Identifier: Apache-2.0
"""The strongest *cheap* deterministic canon linter — and its honest ceiling.

A monolithic canon document is not a typed artifact (ADR-010): it has no
frontmatter identity, no schema, and no relationship graph. This linter is what
a team could reasonably write to police such a document *without* re-building
the engine — a heading-structure scan over the ``## <id> — …`` blocks. It
checks, per block:

- **block-boundary sanity** — every block must open with ``## RAC-…``. A
  ``boundary-break`` strips a heading's ``## ``, so its id line survives as an
  orphan inside the *previous* block; the linter spots that orphan and reports
  the merged (now-unreachable) id.
- **status well-formedness** — the block's status section must exist and its
  first body line must be one of the four decision statuses. A
  ``malformed-status`` (``superceded`` / ``Status : Superseded`` / …) fails.
- **heading discipline** — the status heading must be exactly ``### Status``
  (H3 under the ``##`` block). A ``heading-slip`` to ``#### Status`` fails.
- **duplicate identity** — a full scan of block ids catches a reused id.

What it **cannot** do cheaply, and does not pretend to: resolve a
``Supersedes`` target. A ``- RAC-…`` under a supersedes section may point to a
decision that lives in *another* canon (the requirements document), in a
per-file-only rendering, or be legitimate under the schema's relationship
semantics — the linter has none of that, so flagging every unresolved id would
false-positive on every valid cross-document reference. Reimplementing target
resolution *is* reimplementing the engine's schema registry and graph; the
matrix reports this class as **undetected** and this is why. That is the honest
ceiling the roadmap asks the linter to show, not a loss taken on purpose.

Pure function of the canon text; stdlib only; never imports the engine
(DG-ADR-0001).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The four decision statuses ``rac validate`` accepts (Proposed / Accepted /
# Superseded / Deprecated); anything else is a malformed status.
VALID_STATUSES = frozenset({"Proposed", "Accepted", "Superseded", "Deprecated"})

_BLOCK_HEADING = re.compile(r"^## (RAC-[0-9A-Z]+) — ", re.MULTILINE)
_ID_LINE = re.compile(r"^(RAC-[0-9A-Z]+) — ", re.MULTILINE)
_STATUS_ANY = re.compile(r"^(#+) Status\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Finding:
    """One lint problem: the offending id, a stable code, and the break class."""

    dec_id: str
    code: str
    break_class: str


def _blocks(text: str) -> list[tuple[str, str]]:
    """``(id, block_text)`` per ``## RAC-… — …`` heading, in document order."""
    marks = [(m.group(1), m.start()) for m in _BLOCK_HEADING.finditer(text)]
    out: list[tuple[str, str]] = []
    for i, (dec_id, start) in enumerate(marks):
        end = marks[i + 1][1] if i + 1 < len(marks) else len(text)
        out.append((dec_id, text[start:end]))
    return out


def lint(text: str) -> list[Finding]:
    """Every deterministic finding the canon linter can raise over ``text``."""
    findings: list[Finding] = []
    seen: dict[str, int] = {}

    for dec_id, block in _blocks(text):
        # duplicate identity — a full scan sees the reuse a single block cannot.
        seen[dec_id] = seen.get(dec_id, 0) + 1
        if seen[dec_id] == 2:
            findings.append(Finding(dec_id, "duplicate-id", "duplicate-id"))

        # block-boundary sanity — an orphan id line inside this block is a
        # heading whose ``## `` was stripped: the block it names is unreachable.
        body = block[block.index("\n") + 1 :] if "\n" in block else ""
        for m in _ID_LINE.finditer(body):
            findings.append(
                Finding(m.group(1), "orphan-block-boundary", "boundary-break")
            )

        # heading discipline + status well-formedness.
        sm = _STATUS_ANY.search(block)
        if sm is None:
            findings.append(Finding(dec_id, "missing-status", "heading-slip"))
            continue
        if sm.group(1) != "###":
            findings.append(Finding(dec_id, "status-heading-level", "heading-slip"))
            continue
        value = _first_body_line(block, sm.end())
        if value not in VALID_STATUSES:
            findings.append(Finding(dec_id, "malformed-status", "malformed-status"))

    return findings


def _first_body_line(block: str, after: int) -> str | None:
    """The first non-empty, non-heading line after a status heading."""
    for line in block[after:].splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            return None
        return stripped
    return None


def flagged_ids(findings: list[Finding]) -> set[str]:
    """The set of decision ids the linter would flag (a canon merge-gate set)."""
    return {f.dec_id for f in findings}
