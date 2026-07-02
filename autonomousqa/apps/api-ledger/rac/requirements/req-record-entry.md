---
schema_version: 1
id: LEDGER-0000000000R2
type: requirement
---

# Recording an Entry Returns the Stored Entry

## Status

Accepted

## Problem

Clients need confirmation that a submitted ledger entry was accepted and
stored, including the identifier the service assigned to it.

## Requirements

- [REQ-001] The service SHALL accept `POST /entries` with a JSON body carrying a non-empty string `label` and a non-zero integer `amount`.
- [REQ-002] A successful submission SHALL return HTTP status 201.
- [REQ-003] The response body SHALL echo the submitted `label` and `amount` and SHALL carry the assigned integer `id`.

## Acceptance Criteria

- Posting `{"label": "coffee", "amount": -3}` to `/entries` returns 201.
- The response echoes `label` `"coffee"` and `amount` `-3`.
