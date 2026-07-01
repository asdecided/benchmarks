---
schema_version: 1
id: FDB-FNC5AS3XS0FE
type: decision
tags: [auth, sessions]
---
# Stateless JWT Sessions

## Status

Accepted

## Context

The per-request lookup against the Redis session store became the gateway's dominant latency term, and the store itself a single point of failure. The signed cookie era proved pure client-side state; the server-side era proved revocation. Beacon needs both.

## Decision

Sessions are short-lived signed JWTs verified statelessly at the gateway, paired with a rotating refresh grant checked against a revocation list only at refresh time. This replaces both the signed cookie session record and the Redis session store lookup.

## Consequences

The hot path touches no session storage, and revocation takes effect within one token lifetime. Clock skew between gateway nodes becomes a correctness concern and is bounded by the token lifetime.

## Category

Technical

## Supersedes

- FDB-94ZFJW09ZXMB
