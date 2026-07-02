---
schema_version: 1
id: NOTES-0000000000R3
type: requirement
---

# Empty Notes Are Rejected with a Visible Error

## Status

Accepted

## Problem

An empty note is board clutter with no content. The board must refuse it and
tell the user why. This is a negative-path capability: verifying it means
proving the rejection happens, not that adding works.

## Requirements

- [REQ-001] The board SHALL NOT add a note when the input is empty or only whitespace.
- [REQ-002] The board SHALL show the error message "A note needs some text." when an empty add is attempted.
- [REQ-003] The notes count SHALL be unchanged by a rejected add.

## Acceptance Criteria

- Activating "Add note" with an empty input shows the error banner reading
  "A note needs some text.".
- The count still reads "0 notes" on a fresh board after the rejected add.
