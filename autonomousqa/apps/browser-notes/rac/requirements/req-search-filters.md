---
schema_version: 1
id: NOTES-0000000000R4
type: requirement
---

# Search Filters the Visible Notes

## Status

Accepted

## Problem

A board with many notes is only useful if the user can narrow it to the note
they need, without deleting anything.

## Requirements

- [REQ-001] The board SHALL show only the notes whose text contains the search input's text, case-insensitively, while a search query is present.
- [REQ-002] Filtering SHALL NOT remove notes from the board; clearing the query restores the full list.

## Acceptance Criteria

- With notes "Buy milk" and "Call dad" on the board, searching "milk" leaves
  "Buy milk" visible and hides "Call dad".
- The count line still reports the total number of notes held.
