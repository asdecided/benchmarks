---
schema_version: 1
id: FDB-94ZFJW09ZXMB
type: decision
tags: [auth, sessions]
---
# Redis Server-Side Sessions

## Status

Superseded

## Context

Signed cookie sessions could not be revoked and were outgrowing header limits as claims accumulated.

## Decision

Session records move into a Redis session store keyed by an opaque cookie handle. The gateway looks the handle up on every request and revocation deletes the record.

## Consequences

Instant revocation and small cookies, at the price of a Redis round-trip on every request and a new availability dependency on the session store. Replaced when the lookup became the gateway's dominant latency term.

## Category

Technical

## Supersedes

- FDB-99EJE1VT5PHQ
