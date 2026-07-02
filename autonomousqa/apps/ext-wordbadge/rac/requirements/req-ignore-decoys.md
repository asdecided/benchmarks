---
schema_version: 1
id: BADGE-0000000000R3
type: requirement
---

# Text Outside Main Content Is Never Counted

## Status

Accepted

## Problem

Headers, navigation, and footers are page furniture, not content. A counter
that reads the whole document overcounts. This is a negative-path
capability: verifying it means proving the decoy text did NOT inflate the
count.

## Requirements

- [REQ-001] The badge SHALL NOT count words that sit outside the page's `main` element.
- [REQ-002] On the sample decoys page — twelve words of main content wrapped in heavy header and footer padding — the badge SHALL read "12 words".

## Acceptance Criteria

- Opening `/decoys.html` with the extension loaded shows a badge reading
  exactly "12 words" despite the decoy text around the main region.
