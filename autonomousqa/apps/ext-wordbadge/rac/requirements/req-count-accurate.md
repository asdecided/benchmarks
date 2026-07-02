---
schema_version: 1
id: BADGE-0000000000R2
type: requirement
---

# The Badge Reports the Main Content's Word Count

## Status

Accepted

## Problem

A badge with the wrong number is worse than no badge. The count must equal
the number of words in the page's main content — a word being a
whitespace-separated token containing at least one letter or digit.

## Requirements

- [REQ-001] The badge SHALL report the number of words inside the page's `main` element.
- [REQ-002] On the sample article page, whose main content holds exactly 60 words, the badge SHALL read "60 words".

## Acceptance Criteria

- Opening `/article.html` with the extension loaded shows a badge reading
  exactly "60 words".
