---
schema_version: 1
id: NOTES-0000000000R5
type: requirement
---

# Deleting a Note Removes Exactly That Note

## Status

Accepted

## Problem

Every note carries its own delete control; deleting must remove exactly the
chosen note and keep the count honest. Verifying this takes a multi-step
flow — add two notes, delete one, then prove the survivor and the count —
harder than any single interaction.

## Requirements

- [REQ-001] Each note SHALL carry a delete control whose accessible name is "Delete" followed by the note's text.
- [REQ-002] Activating a note's delete control SHALL remove that note and only that note from the board.
- [REQ-003] The notes count SHALL reflect the removal immediately.

## Acceptance Criteria

- With notes "Buy milk" and "Call dad" on the board, activating
  "Delete Buy milk" leaves "Call dad" visible and the count reading
  "1 note".
