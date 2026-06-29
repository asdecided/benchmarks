"""Deterministic ingest of real W3C Technical Reports into corpus artifacts.

Real/public-derived corpus material (CONTRIBUTING.md rule 2), a third domain
alongside the PEPs and RFCs. A *dated* W3C TR URL (e.g.
`https://www.w3.org/TR/2008/REC-xml-20081126/`) is immutable — W3C never edits a
dated publication in place — so, as with RFCs, the dated id is the pin and the
per-document sha256 recorded in provenance.json catches any drift or tampering.

    python -m ingest.w3c build  --specs 2006/REC-xml-20060816,2008/REC-xml-20081126 \
                                --out scenarios_real/w3c_xml_edition_supersession
    python -m ingest.w3c verify --out scenarios_real/w3c_xml_edition_supersession

`build` fetches each dated TR and writes a RAC-native `decision` artifact: the
canonical decision sections RAC classifies on
(`Status`/`Context`/`Decision`/`Consequences`) plus a directional `Supersedes`
section, then the verbatim TR HTML under `## Source Text`. Every envelope value
is *derived from the document's own header metadata* — W3C TRs carry a header
`<dl>` listing `This version` / `Latest version` / `Previous version(s)`, and the
machine-readable `Previous version` link is the authoritative backward edge
(newer supersedes the dated version it lists), corroborated by the standard
"This edition supersedes the previous W3C Recommendation" prose. A TR that a
newer in-corpus TR lists as a previous version is stamped `Status: Superseded`.

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

_TR_BASE = "https://www.w3.org/TR/"

# The XML edition supersession pilot: XML 1.0 Fifth Edition lists the Fourth
# Edition under `Previous versions` in its own header; the edge is the document's
# own metadata (and its prose states it supersedes the previous Recommendation).
XML_SPECS = ("2006/REC-xml-20060816", "2008/REC-xml-20081126")

SOURCE_TEXT_MARKER = "\n\n## Source Text\n\n"


def spec_segment(path_or_url: str) -> str:
    """The dated shortname segment of a TR path/URL.

    'https://www.w3.org/TR/2008/REC-xml-20081126/' -> 'REC-xml-20081126'
    '2006/REC-xml-20060816'                         -> 'REC-xml-20060816'
    """
    m = re.search(r"([A-Za-z][A-Za-z0-9.+-]*-\d{8})/?$", path_or_url.rstrip("/"))
    if m:
        return m.group(1)
    return path_or_url.rstrip("/").rsplit("/", 1)[-1]


def w3c_id(path_or_url: str) -> str:
    """Stable corpus artifact id for a dated TR (e.g. 'W3C-REC-xml-20081126')."""
    return f"W3C-{spec_segment(path_or_url)}"


def source_url(path: str) -> str:
    """Canonical dated TR URL for a `YYYY/SHORTNAME-YYYYMMDD` path."""
    return f"{_TR_BASE}{path.strip('/')}/"


def fetch_spec(path: str, timeout: float = 30.0) -> str:
    """Fetch one dated TR's canonical HTML, with line endings normalised to LF.

    Some W3C TR pages are served with CRLF; we normalise to LF so the artifact is
    deterministic across platforms and survives git's line-ending handling. The
    sha256 in provenance is taken over this normalised text, so `verify`
    reproduces it byte-for-byte regardless of how the bytes were checked out.
    """
    req = urllib.request.Request(
        source_url(path), headers={"User-Agent": "decisiongrounding-ingest"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - pinned host
        text = resp.read().decode("utf-8", "replace")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _dd_after(html: str, label: str) -> str:
    """The raw HTML of the <dd> following the <dt> whose text starts with
    `label` (e.g. 'Previous version'). Empty string if absent."""
    m = re.search(
        rf"<dt>\s*{re.escape(label)}[^<]*</dt>\s*<dd>(.*?)</dd>", html, re.S | re.I
    )
    return m.group(1) if m else ""


def _hrefs(fragment: str) -> list[str]:
    return re.findall(r'href="([^"]+)"', fragment)


def parse_meta(html: str) -> dict:
    """Header metadata derived from the TR's own `<dl>` and title.

    Returns title, W3C status, the `This version` URL, and the dated segments of
    every `Previous version(s)` link (the machine-readable backward edges).
    """
    title_m = re.search(r"<title>(.*?)</title>", html, re.S | re.I)
    title = re.sub(r"\s+", " ", title_m.group(1)).strip() if title_m else ""
    status_m = re.search(
        r"W3C (Recommendation|Proposed Recommendation|Candidate Recommendation|"
        r"Working Draft|Working Group Note|Note|Proposed Edited Recommendation)",
        html,
    )
    status = status_m.group(1) if status_m else "Recommendation"
    this_dd = _dd_after(html, "This version")
    this_version = (_hrefs(this_dd) or [""])[0]
    prev_dd = _dd_after(html, "Previous version")
    previous_segments = [spec_segment(h) for h in _hrefs(prev_dd)]
    return {
        "title": title,
        "status": status,
        "this_version": this_version,
        "previous_segments": previous_segments,
    }


def corpus_markdown(
    path: str,
    html: str,
    superseded_by: dict[str, str] | None = None,
    in_corpus: frozenset[str] | None = None,
) -> str:
    """A RAC-native `decision` artifact wrapping the verbatim TR HTML.

    Status is derived: a TR listed as a `Previous version` by another TR in the
    same corpus is `Superseded` (with a `## Superseded By` note); otherwise its
    W3C status. The `## Supersedes` section lists this TR's `Previous version`
    segments that are present in the corpus, so no reference dangles.
    """
    seg = spec_segment(path)
    aid = w3c_id(path)
    superseded_by = superseded_by or {}
    in_corpus = in_corpus if in_corpus is not None else frozenset({seg})
    meta = parse_meta(html)
    successor = superseded_by.get(seg)
    status = "Superseded" if successor is not None else meta["status"]
    supersedes = [
        f"W3C-{s}" for s in meta["previous_segments"] if s in in_corpus
    ]
    heading = f"# {aid} — {meta['title']}" if meta["title"] else f"# {aid}"
    parts = [
        "---",
        "schema_version: 1",
        f"id: {aid}",
        "type: decision",
        "tags: [w3c]",
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
        f"Public decision ingested verbatim from the W3C Technical Reports archive",
        f"({source_url(path)}). Dated W3C TRs are immutable, so the dated id is the",
        f"pin and the upstream sha256 is recorded in provenance.json. Upstream W3C",
        f"status: {meta['status']}. The RAC envelope sections are derived from the",
        "document's own header metadata; the authoritative content is the unedited",
        "TR reproduced under Source Text.",
        "",
        "## Decision",
        "",
        "Defined by the verbatim W3C TR under Source Text below.",
        "",
        "## Consequences",
        "",
        "As stated by the upstream TR; see Source Text.",
    ]
    if successor is not None:
        parts += ["", "## Superseded By", "", f"- W3C-{successor}"]
    if supersedes:
        parts += ["", "## Supersedes", ""] + [f"- {sid}" for sid in supersedes]
    envelope = "\n".join(parts)
    return envelope + SOURCE_TEXT_MARKER + html


def _superseded_by(specs: tuple[str, ...], metas: dict[str, dict]) -> dict[str, str]:
    """Map each superseded segment -> the in-corpus segment that supersedes it,
    derived from the newer TR's `Previous version` links."""
    in_corpus = frozenset(spec_segment(s) for s in specs)
    out: dict[str, str] = {}
    for path in specs:
        seg = spec_segment(path)
        for prev in metas[path]["previous_segments"]:
            if prev in in_corpus:
                out[prev] = seg
    return out


def build_provenance(specs: tuple[str, ...], htmls: dict[str, str], metas: dict[str, dict]) -> dict:
    """The auditable record: per-spec hashes, header metadata, and derived edges."""
    in_corpus = frozenset(spec_segment(s) for s in specs)
    entries = []
    edges = []
    for path in specs:
        seg = spec_segment(path)
        meta = metas[path]
        entries.append(
            {
                "id": w3c_id(path),
                "segment": seg,
                "file": f"corpus/{w3c_id(path)}.md",
                "url": source_url(path),
                "source_sha256": hashlib.sha256(htmls[path].encode("utf-8")).hexdigest(),
                "status": meta["status"],
                "title": meta["title"],
                "previous_versions": meta["previous_segments"],
                "replaces": [f"W3C-{s}" for s in meta["previous_segments"] if s in in_corpus],
            }
        )
        for prev in meta["previous_segments"]:
            if prev in in_corpus:
                edges.append({"source": w3c_id(path), "type": "supersedes", "target": f"W3C-{prev}"})
    return {
        "source": "w3.org/TR",
        "immutable": True,
        "specs": entries,
        "supersedes_edges": edges,
    }


def build(out_dir: Path, specs: tuple[str, ...] = XML_SPECS, skip_missing: bool = False) -> dict:
    """Fetch the dated TRs and write corpus files + provenance.json."""
    corpus_dir = out_dir / "corpus"
    corpus_dir.mkdir(parents=True, exist_ok=True)
    htmls: dict[str, str] = {}
    for path in specs:
        try:
            htmls[path] = fetch_spec(path)
        except Exception:  # noqa: BLE001 - tolerate gaps only when asked
            if not skip_missing:
                raise
    included = tuple(p for p in specs if p in htmls)
    metas = {p: parse_meta(htmls[p]) for p in included}
    superseded_by = _superseded_by(included, metas)
    in_corpus = frozenset(spec_segment(p) for p in included)
    for path in included:
        (corpus_dir / f"{w3c_id(path)}.md").write_text(
            corpus_markdown(path, htmls[path], superseded_by, in_corpus), encoding="utf-8"
        )
    provenance = build_provenance(included, htmls, metas)
    (out_dir / "provenance.json").write_text(
        json.dumps(provenance, indent=2) + "\n", encoding="utf-8"
    )
    return provenance


def verify(out_dir: Path) -> list[str]:
    """Re-fetch each dated TR; return integrity problems (empty == reproduces)."""
    provenance = json.loads((out_dir / "provenance.json").read_text(encoding="utf-8"))
    specs = tuple(e["url"].removeprefix(_TR_BASE).strip("/") for e in provenance["specs"])
    htmls: dict[str, str] = {}
    problems: list[str] = []
    for entry, path in zip(provenance["specs"], specs):
        try:
            html = fetch_spec(path)
        except Exception as exc:  # noqa: BLE001 - report, don't crash
            problems.append(f"{entry['id']}: fetch failed: {exc}")
            continue
        htmls[path] = html
        got = hashlib.sha256(html.encode("utf-8")).hexdigest()
        if got != entry["source_sha256"]:
            problems.append(
                f"{entry['id']}: upstream sha256 changed ({got} != {entry['source_sha256']})"
            )
    if htmls:
        included = tuple(p for p in specs if p in htmls)
        metas = {p: parse_meta(htmls[p]) for p in included}
        superseded_by = _superseded_by(included, metas)
        in_corpus = frozenset(spec_segment(p) for p in included)
        for entry, path in zip(provenance["specs"], specs):
            if path not in htmls:
                continue
            expected = corpus_markdown(path, htmls[path], superseded_by, in_corpus)
            actual = (out_dir / entry["file"]).read_text(encoding="utf-8")
            if expected != actual:
                problems.append(f"{entry['id']}: committed {entry['file']} does not match upstream bytes")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ingest.w3c", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("build", "verify"):
        sp = sub.add_parser(name)
        sp.add_argument("--out", required=True, help="scenario directory to write/verify")
        if name == "build":
            sp.add_argument(
                "--specs",
                default=",".join(XML_SPECS),
                help="comma-separated dated TR paths, e.g. 2008/REC-xml-20081126 "
                "(default: the XML edition pair)",
            )
    args = parser.parse_args(argv)
    out_dir = Path(args.out)

    if args.cmd == "build":
        specs = tuple(s.strip() for s in args.specs.split(",") if s.strip())
        provenance = build(out_dir, specs)
        print(f"wrote {len(provenance['specs'])} W3C TR corpus file(s) + provenance.json to {out_dir}")
        for edge in provenance["supersedes_edges"]:
            print(f"  edge: {edge['source']} supersedes {edge['target']}")
        return 0

    problems = verify(out_dir)
    if problems:
        print("verify FAILED:", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        return 1
    print(f"verify OK: corpus in {out_dir} reproduces from w3.org/TR")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
