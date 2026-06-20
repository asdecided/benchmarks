"""Hermetic unit tests for the RFC ingest header parsing + edge derivation.
No network: they exercise the deterministic parsing on a representative header
block. The end-to-end fetch/reproduce path is covered by `ingest.rfcs verify`."""

from ingest.rfcs import (
    corpus_markdown,
    obsoletes_targets,
    parse_header_fields,
    rfc_id,
)

# A representative RFC header block (two-column: left fields, right author/date)
# followed by a centered title and body, like rfc-editor.org plain text.
_SAMPLE = (
    "Internet Engineering Task Force (IETF)                       E. Rescorla\n"
    "Request for Comments: 8446                                       Mozilla\n"
    "Obsoletes: 5077, 5246, 6961                                   August 2018\n"
    "Category: Standards Track\n"
    "ISSN: 2070-1721\n"
    "\n"
    "          The Transport Layer Security (TLS) Protocol Version 1.3\n"
    "\n"
    "Abstract\n"
    "\n"
    "   This document specifies version 1.3 of the TLS protocol.\n"
)


def test_rfc_id_zero_pads():
    assert rfc_id(8446) == "RFC-8446"


def test_parse_strips_right_column_bleed():
    fields = parse_header_fields(_SAMPLE)
    # The author/date right column must not bleed into the value.
    assert fields["Category"] == "Standards Track"
    assert fields["Obsoletes"].startswith("5077, 5246, 6961")
    assert "August" not in fields["Obsoletes"]


def test_obsoletes_targets_are_numeric_only():
    assert obsoletes_targets(parse_header_fields(_SAMPLE)) == [5077, 5246, 6961]


def test_corpus_markdown_marks_superseded_and_supersedes_within_corpus():
    in_corpus = frozenset({5246, 8446})
    # 8446 obsoletes 5246 -> 5246 is Superseded By 8446; 8446 Supersedes 5246.
    successor = corpus_markdown(8446, _SAMPLE, {5246: 8446}, in_corpus)
    assert "## Supersedes" in successor and "RFC-5246" in successor
    assert "## Source Text" in successor
    # A target outside the corpus (6961) must not dangle.
    assert "RFC-6961" not in successor.split("## Source Text")[0]


def test_corpus_markdown_superseded_status_is_derived():
    # When 5246 is obsoleted by something in-corpus, its envelope is Superseded.
    body = corpus_markdown(5246, _SAMPLE.replace("8446", "5246"), {5246: 8446}, frozenset({5246, 8446}))
    head = body.split("## Source Text")[0]
    assert "Superseded" in head and "## Superseded By" in head
