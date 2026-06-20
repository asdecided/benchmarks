"""Deterministic ingest of real IETF RFCs into corpus artifacts.

Real/public-derived corpus material (CONTRIBUTING.md rule 2), a second domain
alongside the PEPs (see `ingest/peps.py`). RFCs are immutable by IETF policy —
a published RFC's text never changes — so unlike PEPs there is no commit to pin:
the RFC number *is* the pin, and the per-RFC sha256 recorded in provenance.json
catches any drift or local tampering.

    python -m ingest.rfcs build  --rfcs 5246,8446 --out scenarios_real/rfc_tls_version_supersession
    python -m ingest.rfcs verify --out scenarios_real/rfc_tls_version_supersession

`build` fetches each RFC's canonical text and writes a RAC-native `decision`
artifact: the canonical decision sections RAC classifies on
(`Status`/`Context`/`Decision`/`Consequences`) plus a directional `Supersedes`
section, then the verbatim RFC under `## Source Text`. Every envelope value is
*derived from the RFC's own header fields* — its `Obsoletes:` header is the
authoritative forward edge (newer obsoletes older). An RFC that another RFC in
the same corpus obsoletes is stamped `Status: Superseded` (the obsoletion is a
public fact stated in the obsoleting RFC's header); otherwise `Status: Final`.

The task and gold label in `scenario.json` are authored by hand, blind to arm
outputs (rule 1). This tool never writes them.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

_RFC_URL = "https://www.rfc-editor.org/rfc/rfc{num}.txt"

# The TLS supersession pilot: RFC 8446 (TLS 1.3, Standards Track) Obsoletes RFC
# 5246 (TLS 1.2); the edge is stated in 8446's own `Obsoletes:` header.
TLS_RFCS = (5246, 8446)

# The RFC distractor pool range for the real N-curve. RFCs are dense, so 1..400
# yields enough real RFC decisions to support N up to 300; the range is the
# pinned knob and the included set is recorded in provenance.json. Mirrors the
# PEP pool (ingest/peps.py POOL_RANGE).
POOL_RANGE = (1, 400)
_DEFAULT_POOL_OUT = Path(__file__).resolve().parent.parent / "scenarios_real" / "rfcs_pool"

SOURCE_TEXT_MARKER = "\n\n## Source Text\n\n"


def rfc_id(num: int) -> str:
    """Stable corpus artifact id for an RFC number (e.g. 8446 -> 'RFC-8446')."""
    return f"RFC-{num:04d}"


def source_url(num: int) -> str:
    return _RFC_URL.format(num=num)


def fetch_rfc(num: int, timeout: float = 25.0) -> str:
    """Fetch one RFC's canonical plain text."""
    req = urllib.request.Request(
        source_url(num), headers={"User-Agent": "decisiongrounding-ingest"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - pinned host
        return resp.read().decode("utf-8", "replace")


def parse_header_fields(txt: str) -> dict[str, str]:
    """Parse the left-column `Key: value` fields in an RFC's top header block.

    RFC text opens with a two-column header (org/author on the right, metadata
    like `Request for Comments:`, `Obsoletes:`, `Updates:`, `Category:` on the
    left). We read those `Key: value` fields from the first lines, stopping at
    the first all-blank gap that precedes the centered title.
    """
    fields: dict[str, str] = {}
    seen_field = False
    for line in txt.splitlines()[:40]:
        if line.strip() == "":
            if seen_field:
                break
            continue
        m = re.match(r"^([A-Za-z][A-Za-z /]+):\s+(.*\S)", line)
        if m:
            seen_field = True
            key = m.group(1).strip()
            # The right column (author/date) bleeds into the line; a run of 2+
            # spaces separates the left field value from it, so cut there.
            value = re.split(r"\s{2,}", m.group(2))[0].strip()
            fields.setdefault(key, value)
    return fields


def _field_numbers(fields: dict[str, str], key: str) -> list[int]:
    """RFC numbers from a header value like 'Obsoletes: 5077, 5246, 6961  ...'."""
    raw = fields.get(key, "")
    nums: list[int] = []
    for tok in re.split(r"[,\s]+", raw):
        if tok.isdigit():
            nums.append(int(tok))
        elif nums:
            break  # stop once the right-column text starts
    return nums


def obsoletes_targets(fields: dict[str, str]) -> list[int]:
    """RFC numbers this RFC obsoletes, per its own `Obsoletes:` header."""
    return _field_numbers(fields, "Obsoletes")


def _title(txt: str) -> str:
    """Best-effort document title: the first centered (indented) non-field line
    after the header block. Cosmetic only — nothing functional depends on it."""
    started = False
    for line in txt.splitlines()[:60]:
        s = line.strip()
        if not s:
            started = True
            continue
        if started and not re.match(r"^[A-Za-z][A-Za-z /]+:\s", line) and line.startswith(" "):
            return s
    return ""


def corpus_markdown(
    num: int,
    txt: str,
    obsoleted_by: dict[int, int] | None = None,
    in_corpus: frozenset[int] | None = None,
) -> str:
    """A RAC-native `decision` artifact wrapping the verbatim RFC.

    Status is derived: an RFC obsoleted by another RFC in the same corpus is
    `Superseded` (with a `## Superseded By` note); otherwise `Final`. The
    `## Supersedes` section lists this RFC's `Obsoletes` targets that are present
    in the corpus, so no reference dangles. Nothing here editorialises the RFC's
    technical content — the authoritative text is reproduced verbatim below.
    """
    fields = parse_header_fields(txt)
    obsoleted_by = obsoleted_by or {}
    in_corpus = in_corpus if in_corpus is not None else frozenset({num})
    category = fields.get("Category", "").strip()
    superseded_by = obsoleted_by.get(num)
    status = "Superseded" if superseded_by is not None else "Final"
    supersedes = [rfc_id(t) for t in obsoletes_targets(fields) if t in in_corpus]
    title = _title(txt)

    heading = f"# {rfc_id(num)} — {title}" if title else f"# {rfc_id(num)}"
    parts = [
        "---",
        "schema_version: 1",
        f"id: {rfc_id(num)}",
        "type: decision",
        "tags: [rfc]",
        "---",
        "",
        heading,
        "",
        "## Status",
        "",
        status,
        "",
        "## Context",
        "",
        f"Public decision ingested verbatim from the RFC Editor (RFC {num});",
        f"source {source_url(num)}. RFCs are immutable, so the RFC number is the",
        f"pin and the upstream sha256 is recorded in provenance.json. Upstream",
        f"category: {category or 'n/a'}. The RAC envelope sections are derived from",
        "the RFC's own header fields; the authoritative content is the unedited RFC",
        "reproduced under Source Text.",
        "",
        "## Decision",
        "",
        "Defined by the verbatim RFC text under Source Text below.",
        "",
        "## Consequences",
        "",
        "As stated by the upstream RFC; see Source Text.",
    ]
    if superseded_by is not None:
        parts += ["", "## Superseded By", "", f"- {rfc_id(superseded_by)}"]
    if supersedes:
        parts += ["", "## Supersedes", ""] + [f"- {sid}" for sid in supersedes]
    envelope = "\n".join(parts)
    return envelope + SOURCE_TEXT_MARKER + txt


def _edges_within(rfcs: tuple[int, ...], texts: dict[int, str]) -> list[dict]:
    """Supersedes edges among the corpus, derived from each RFC's Obsoletes."""
    in_corpus = frozenset(rfcs)
    edges = []
    for num in rfcs:
        for target in obsoletes_targets(parse_header_fields(texts[num])):
            if target in in_corpus:
                edges.append({"source": rfc_id(num), "type": "supersedes", "target": rfc_id(target)})
    return edges


def build_provenance(rfcs: tuple[int, ...], texts: dict[int, str]) -> dict:
    """The auditable record: per-RFC hashes, headers, and derived edges."""
    entries = []
    for num in rfcs:
        txt = texts[num]
        fields = parse_header_fields(txt)
        entries.append(
            {
                "id": rfc_id(num),
                "number": num,
                "file": f"corpus/{rfc_id(num)}.md",
                "url": source_url(num),
                "source_sha256": hashlib.sha256(txt.encode("utf-8")).hexdigest(),
                "category": fields.get("Category", ""),
                "title": _title(txt),
                "obsoletes": [rfc_id(n) for n in obsoletes_targets(fields)],
                "replaces": [
                    rfc_id(n) for n in obsoletes_targets(fields) if n in frozenset(rfcs)
                ],
            }
        )
    return {
        "source": "rfc-editor.org",
        "immutable": True,
        "rfcs": entries,
        "supersedes_edges": _edges_within(rfcs, texts),
    }


def build(out_dir: Path, rfcs: tuple[int, ...] = TLS_RFCS, skip_missing: bool = False) -> dict:
    """Fetch the RFCs and write corpus files + provenance.json."""
    corpus_dir = out_dir / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    texts: dict[int, str] = {}
    for num in rfcs:
        try:
            texts[num] = fetch_rfc(num)
        except Exception:  # noqa: BLE001 - tolerate gaps only when asked
            if not skip_missing:
                raise
    included = tuple(num for num in rfcs if num in texts)
    in_corpus = frozenset(included)
    obsoleted_by = {
        n: src
        for num in included
        for n in obsoletes_targets(parse_header_fields(texts[num]))
        if n in in_corpus
        for src in (num,)
    }
    for num in included:
        (corpus_dir / f"{rfc_id(num)}.md").write_text(
            corpus_markdown(num, texts[num], obsoleted_by, in_corpus), encoding="utf-8"
        )
    provenance = build_provenance(included, texts)
    (out_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    return provenance


def verify(out_dir: Path) -> list[str]:
    """Re-fetch each RFC; return integrity problems (empty == reproduces)."""
    provenance = json.loads((out_dir / "provenance.json").read_text(encoding="utf-8"))
    rfcs = tuple(e["number"] for e in provenance["rfcs"])
    in_corpus = frozenset(rfcs)
    texts: dict[int, str] = {}
    problems: list[str] = []
    for entry in provenance["rfcs"]:
        num = entry["number"]
        try:
            txt = fetch_rfc(num)
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            problems.append(f"{entry['id']}: fetch failed: {exc}")
            continue
        texts[num] = txt
        got = hashlib.sha256(txt.encode("utf-8")).hexdigest()
        if got != entry["source_sha256"]:
            problems.append(
                f"{entry['id']}: upstream sha256 changed ({got} != {entry['source_sha256']})"
            )
    if texts:
        obsoleted_by = {
            n: src
            for num in texts
            for n in obsoletes_targets(parse_header_fields(texts[num]))
            if n in in_corpus
            for src in (num,)
        }
        for entry in provenance["rfcs"]:
            num = entry["number"]
            if num not in texts:
                continue
            expected = corpus_markdown(num, texts[num], obsoleted_by, in_corpus)
            actual = (out_dir / entry["file"]).read_text(encoding="utf-8")
            if expected != actual:
                problems.append(f"{entry['id']}: committed {entry['file']} does not match upstream bytes")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingest.rfcs", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("build", "verify"):
        sp = sub.add_parser(name)
        sp.add_argument("--out", required=True, help="scenario directory to write/verify")
        if name == "build":
            sp.add_argument(
                "--rfcs",
                default=",".join(str(n) for n in TLS_RFCS),
                help="comma-separated RFC numbers (default: the TLS pair 5246,8446)",
            )
    pool = sub.add_parser("pool", help="build/verify the real RFC distractor pool")
    pool.add_argument("pool_cmd", choices=["build", "verify"])
    pool.add_argument("--out", default=str(_DEFAULT_POOL_OUT), help="pool directory")
    pool.add_argument(
        "--range",
        dest="range_",
        default=f"{POOL_RANGE[0]}-{POOL_RANGE[1]}",
        help="inclusive RFC number range to scan, e.g. 1-400 (the pinned knob)",
    )
    args = parser.parse_args(argv)
    out_dir = Path(args.out)

    if args.cmd == "pool":
        if args.pool_cmd == "build":
            lo, _, hi = args.range_.partition("-")
            rfcs = tuple(range(int(lo), int(hi) + 1))
            provenance = build(out_dir, rfcs, skip_missing=True)
            print(
                f"built real RFC pool: {len(provenance['rfcs'])} RFC decision "
                f"artifacts (scanned {args.range_}, skipped gaps) + provenance.json "
                f"in {out_dir}"
            )
            print(f"  {len(provenance['supersedes_edges'])} real supersedes edge(s) within the pool")
            return 0
        problems = verify(out_dir)
        if problems:
            print("pool verify FAILED:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1
        prov = json.loads((out_dir / "provenance.json").read_text(encoding="utf-8"))
        print(f"pool verify OK: {len(prov['rfcs'])} RFCs reproduce from rfc-editor.org")
        return 0

    if args.cmd == "build":
        rfcs = tuple(int(x) for x in args.rfcs.split(",") if x.strip())
        provenance = build(out_dir, rfcs)
        print(f"wrote {len(provenance['rfcs'])} RFC corpus file(s) + provenance.json to {out_dir}")
        for edge in provenance["supersedes_edges"]:
            print(f"  edge: {edge['source']} supersedes {edge['target']}")
        return 0

    problems = verify(out_dir)
    if problems:
        print("verify FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"verify OK: corpus in {out_dir} reproduces from rfc-editor.org")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
