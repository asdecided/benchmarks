---
schema_version: 1
id: BADGE-0000000000R1
type: requirement
---

# The Badge Appears on Pages with Main Content

## Status

Accepted

## Problem

The extension's whole value is a visible badge; if it fails to appear on an
ordinary content page, nothing else about it matters.

## Requirements

- [REQ-001] The extension SHALL inject a badge element onto every page that contains a `main` element.
- [REQ-002] The badge SHALL be visible without any user interaction and SHALL read as a word count of the form "N words".

## Acceptance Criteria

- Opening `/article.html` with the extension loaded shows the badge.
