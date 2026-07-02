---
schema_version: 1
id: LEDGER-0000000000R5
type: requirement
---

# Balance Reflects Recorded Entries

## Status

Accepted

## Problem

The balance is the ledger's headline answer; it must equal the sum of the
recorded amounts. Verifying this needs a multi-step flow: establish a known
state, record entries, and check the derived total — harder than any single
request/response check.

## Requirements

- [REQ-001] The service SHALL report, at `GET /balance`, a JSON `balance` field equal to the sum of all recorded entry amounts.
- [REQ-002] After `POST /reset`, the reported `balance` SHALL be zero until a new entry is recorded.

## Acceptance Criteria

- After `POST /reset`, then recording amounts 10 and -3, `GET /balance`
  returns `balance` equal to 7.
- Immediately after `POST /reset`, `GET /balance` returns `balance` 0.
