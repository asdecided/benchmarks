---
schema_version: 1
id: TALLY-0000000000R3
type: requirement
---

# Non-Numeric Input Is Refused with a Named Token

## Status

Accepted

## Problem

Silently coercing or skipping a bad token would corrupt the arithmetic. The
tool must refuse, name the offending token, and signal failure through its
exit code. This is a negative-path capability: verifying it means proving the
refusal, not the arithmetic.

## Requirements

- [REQ-001] The tool SHALL exit with code 2 when any argument to a numeric command is not an integer.
- [REQ-002] The refusal SHALL name the offending token on stderr in the form `tally: 'x' is not a number`.

## Acceptance Criteria

- Running `tally.py sum 3 x` exits 2 with stderr containing
  `tally: 'x' is not a number`.
