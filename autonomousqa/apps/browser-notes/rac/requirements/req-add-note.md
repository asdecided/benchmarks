---
schema_version: 1
id: NOTES-0000000000R1
type: requirement
---

# Adding a Note Shows It on the Board

## Status

Accepted

## Problem

The board's core promise is that a note written into the input appears in the
list the moment it is added.

## Requirements

- [REQ-001] The board SHALL append the entered text to the notes list when the user activates the "Add note" button.
- [REQ-002] The added note SHALL be visible on the board immediately, without a page reload.

## Acceptance Criteria

- Typing "Buy milk" and activating "Add note" makes a note reading
  "Buy milk" visible in the list.
