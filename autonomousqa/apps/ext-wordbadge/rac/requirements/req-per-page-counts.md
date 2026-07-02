---
schema_version: 1
id: BADGE-0000000000R4
type: requirement
---

# Each Page Gets Its Own Count, and Punctuation Is Not a Word

## Status

Accepted

## Problem

The badge must be recomputed per page, and its tokenizer must not count
punctuation-only tokens (a dash is not a word). Verifying this takes a
multi-page flow with two different exact counts, one of them on a page
salted with punctuation tokens.

## Requirements

- [REQ-001] The badge SHALL recompute its count on every page load.
- [REQ-002] Whitespace-separated tokens containing no letter or digit SHALL NOT be counted as words.
- [REQ-003] On the sample poem page — 24 words interleaved with bare dashes — the badge SHALL read "24 words", while the article page reads "60 words" in the same browsing session.

## Acceptance Criteria

- Opening `/article.html` shows "60 words"; navigating to `/poem.html` in the
  same session shows "24 words".
