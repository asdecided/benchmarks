---
schema_version: 1
id: FDB-99EJE1VT5PHQ
type: decision
tags: [auth, sessions]
---
# Signed Cookie Sessions

## Status

Superseded

## Context

Beacon's first sign-in shipped before any shared server state existed. Session persistence had to live entirely in the browser.

## Decision

The whole session record is stored in a signed cookie. The gateway verifies the signature on every request; nothing is looked up server-side.

## Consequences

Zero storage footprint, but the cookie grows with every claim added, and revocation before expiry is impossible. Replaced when server-side state became available.

## Category

Technical
