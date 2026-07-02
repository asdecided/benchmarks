---
schema_version: 1
id: NOTES-0000000000R2
type: requirement
---

# The Notes Count Tracks the Board

## Status

Accepted

## Problem

Users judge the size of their board from the count line; a count that drifts
from the list destroys trust in the board.

## Requirements

- [REQ-001] The board SHALL display a count of the notes currently held.
- [REQ-002] The count SHALL read "1 note" for a single note and "N notes" otherwise, updating whenever a note is added.

## Acceptance Criteria

- A fresh board shows "0 notes".
- After adding one note the count reads "1 note".
