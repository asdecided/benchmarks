---
schema_version: 1
id: LEDGER-0000000000R3
type: requirement
---

# Invalid Amounts Are Rejected

## Status

Accepted

## Problem

A ledger that silently accepts malformed amounts corrupts every balance
derived from it. Rejection must be explicit and machine-readable so clients
can correct their input. This is a negative-path capability: verifying it
means proving the service refuses bad input, not that it accepts good input.

## Requirements

- [REQ-001] The service SHALL reject `POST /entries` whose `amount` is zero, missing, or not an integer, with HTTP status 400.
- [REQ-002] The rejection body SHALL be JSON whose `error.code` field equals `invalid_amount`.

## Acceptance Criteria

- Posting `{"label": "oops", "amount": 0}` to `/entries` returns 400.
- The JSON error body carries `error.code` equal to `"invalid_amount"`.
