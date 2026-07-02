---
schema_version: 1
id: LEDGER-0000000000R4
type: requirement
---

# Unknown Entry Lookups Return Not Found

## Status

Accepted

## Problem

Clients following stale references need a definitive, machine-readable signal
that an entry does not exist, distinct from a server failure. This is a
negative-path capability.

## Requirements

- [REQ-001] The service SHALL respond to `GET /entries/<id>` for an id that was never assigned with HTTP status 404.
- [REQ-002] The response body SHALL be JSON whose `error.code` field equals `not_found`.

## Acceptance Criteria

- Requesting `/entries/999999` returns status 404.
- The JSON error body carries `error.code` equal to `"not_found"`.
