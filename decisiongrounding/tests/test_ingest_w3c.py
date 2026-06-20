"""Hermetic unit tests for the W3C ingest header parsing + edge derivation.
No network: they exercise the deterministic parsing on a representative header
block. The end-to-end fetch/reproduce path is covered by `ingest.w3c verify`."""

from ingest.w3c import corpus_markdown, parse_meta, spec_segment, w3c_id

# A representative W3C TR header `<dl>` (as served at w3.org/TR), trimmed.
_SAMPLE = (
    "<title>Extensible Markup Language (XML) 1.0 (Fifth Edition)</title>"
    "<body><p>W3C Recommendation 26 November 2008</p>"
    "<dl><dt>This version:</dt><dd>"
    ' <a href="https://www.w3.org/TR/2008/REC-xml-20081126/">x</a> </dd>'
    "<dt>Latest version:</dt><dd>"
    ' <a href="https://www.w3.org/TR/xml/">x</a> </dd>'
    "<dt>Previous versions:</dt><dd>"
    ' <a href="https://www.w3.org/TR/2008/PER-xml-20080205/">x</a> <br />'
    ' <a href="https://www.w3.org/TR/2006/REC-xml-20060816/">x</a> </dd>'
    "</dl></body>"
)


def test_spec_segment_and_id():
    assert spec_segment("https://www.w3.org/TR/2008/REC-xml-20081126/") == "REC-xml-20081126"
    assert w3c_id("2008/REC-xml-20081126") == "W3C-REC-xml-20081126"


def test_parse_meta_extracts_title_status_and_previous_segments():
    meta = parse_meta(_SAMPLE)
    assert meta["status"] == "Recommendation"
    assert "Fifth Edition" in meta["title"]
    # Previous-version dated segments are read from the document's own header.
    assert meta["previous_segments"] == ["PER-xml-20080205", "REC-xml-20060816"]


def test_corpus_markdown_supersedes_only_in_corpus_targets():
    in_corpus = frozenset({"REC-xml-20060816", "REC-xml-20081126"})
    md = corpus_markdown("2008/REC-xml-20081126", _SAMPLE, {"REC-xml-20060816": "REC-xml-20081126"}, in_corpus)
    head = md.split("## Source Text")[0]
    # The in-corpus previous version is listed; the out-of-corpus PER is not.
    assert "## Supersedes" in head and "W3C-REC-xml-20060816" in head
    assert "PER-xml-20080205" not in head
    assert "## Source Text" in md


def test_corpus_markdown_marks_superseded_predecessor():
    in_corpus = frozenset({"REC-xml-20060816", "REC-xml-20081126"})
    md = corpus_markdown("2006/REC-xml-20060816", _SAMPLE, {"REC-xml-20060816": "REC-xml-20081126"}, in_corpus)
    head = md.split("## Source Text")[0]
    assert "Superseded" in head and "## Superseded By" in head
