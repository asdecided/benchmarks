---
schema_version: 1
id: LEDGER-0000000000R1
type: requirement
---

# Health Endpoint Reports Service Status

## Status

Accepted

## Problem

Operators and integration harnesses need a fast, unauthenticated way to
confirm the ledger service is up before sending traffic to it.

## Requirements

- [REQ-001] The service SHALL respond to `GET /health` with HTTP status 200.
- [REQ-002] The health response body SHALL be JSON whose `status` field equals `ok`.

## Acceptance Criteria

- Requesting `GET /health` returns status code 200.
- The JSON body carries `status` equal to `"ok"`.
