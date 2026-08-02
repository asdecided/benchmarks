#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Build the per-example RAC decision corpora from GitChameleon problem rows.

For each problem, the *governing decision* is the version pin the code must
respect: "this codebase targets ``<library>==<version>`` on Python
``<python_version>``". The builder writes that decision plus a deterministic
set of distractor pins (other examples' decisions) into a per-example corpus
directory, so the As Decided arm's grounding retrieval has to find the governing pin
among plausible competitors — the same distractor model decisiongrounding
uses.

Honesty boundary: a decision artifact carries ONLY what a real recorded
decision would — the pin, its rationale, the extra dependency pins, and the
documentation links from the dataset row. It never carries the problem's
solution, the target function name, or the tests.

Deterministic throughout: artifact ids are Crockford-base32 digests of the
example id, and distractor selection is hash-based — no randomness, no clock.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
ID_PREFIX = "GCB"
DEFAULT_DISTRACTORS = 5

HERE = Path(__file__).resolve().parent


def artifact_id(example_id: str) -> str:
    digest = hashlib.sha256(f"gitchameleon-pin-{example_id}".encode()).digest()
    return ID_PREFIX + "-" + "".join(CROCKFORD[b % 32] for b in digest[:12])


def decision_markdown(row: dict) -> str:
    """One version-pin decision artifact, schema-valid for `decided validate`."""
    library = row["library"]
    version = row["version"]
    python_version = row["python_version"]
    extra = (row.get("additional_dependencies") or "").strip()
    docs = row.get("docs") or []

    consequences = (
        f"All code written for this codebase must target the {library} {version} "
        "API surface: interfaces added after this release are unavailable, and "
        "interfaces this release deprecates or changes must be used in their "
        f"{version} form. Upgrading the pin is a new decision, not a code change."
    )
    context = (
        f"This codebase runs on Python {python_version} and depends on "
        f"{library}. The team pins the library so behaviour is reproducible "
        "across environments; the pinned release, not the latest documentation, "
        "governs which APIs exist and how they behave."
    )
    decision = f"Pin {library} to version {version} on Python {python_version}."
    if extra:
        decision += f" Companion pins: {extra}."

    lines = [
        "---",
        "schema_version: 1",
        f"id: {artifact_id(row['example_id'])}",
        "type: decision",
        "---",
        f"# Library Version Pin: {library} {version}",
        "",
        "## Status",
        "",
        "Accepted",
        "",
        "## Context",
        "",
        context,
        "",
        "## Decision",
        "",
        decision,
        "",
        "## Consequences",
        "",
        consequences,
        "",
        "## Category",
        "",
        "Technical",
    ]
    if docs:
        lines += ["", "## References", ""]
        lines += [f"- {url}" for url in docs]
    return "\n".join(lines) + "\n"


def pick_distractors(rows: list[dict], target: dict, count: int) -> list[dict]:
    """Deterministic distractor pins for one example.

    Candidates are every other example's pin, ranked by a stable digest of the
    (target, candidate) pair; candidates from *other libraries* are taken
    first so a small corpus stays retrievable, and same-library different
    -version pins (the hard, realistic competitors) fill the remainder.
    """
    def rank(candidate: dict) -> str:
        return hashlib.sha256(
            f"{target['example_id']}::{candidate['example_id']}".encode()
        ).hexdigest()

    others = [row for row in rows if row["example_id"] != target["example_id"]]
    other_library = sorted(
        (row for row in others if row["library"] != target["library"]), key=rank
    )
    same_library = sorted(
        (row for row in others if row["library"] == target["library"]), key=rank
    )
    picked: list[dict] = []
    seen_pins: set[tuple[str, str]] = {(target["library"], target["version"])}
    for candidate in other_library + same_library:
        pin = (candidate["library"], candidate["version"])
        if pin in seen_pins:
            continue
        seen_pins.add(pin)
        picked.append(candidate)
        if len(picked) == count:
            break
    return picked


def build(rows: list[dict], out_dir: Path, distractors: int = DEFAULT_DISTRACTORS) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    for row in rows:
        example_dir = out_dir / f"example-{row['example_id']}"
        example_dir.mkdir(parents=True, exist_ok=True)
        members = [row] + pick_distractors(rows, row, distractors)
        for member in members:
            slug = f"pin-{member['library']}-{member['version']}".replace(".", "-")
            (example_dir / f"{slug}.md").write_text(
                decision_markdown(member), encoding="utf-8"
            )
    return len(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--dataset",
        default=str(HERE / "dataset" / "problems.json"),
        help="Problem rows (fetch_dataset.py output, or the committed fixture).",
    )
    parser.add_argument(
        "--out",
        default=str(HERE / "corpus-build"),
        help="Output root for the per-example corpus directories.",
    )
    parser.add_argument(
        "--distractors",
        type=int,
        default=DEFAULT_DISTRACTORS,
        help="Distractor pins per example corpus.",
    )
    args = parser.parse_args()

    payload = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    rows = payload["rows"] if isinstance(payload, dict) else payload
    built = build(rows, Path(args.out), args.distractors)
    print(f"built {built} per-example corpora -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
