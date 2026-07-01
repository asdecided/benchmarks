---
schema_version: 1
id: FDB-Q1G6QMGGX897
type: decision
tags: [traffic]
---
# Fixed Window Rate Limits

## Status

Superseded

## Context

The first abuse incident needed a limiter the same week. A per-minute counter was the fastest correct thing to ship.

## Decision

Each client key gets a counter that resets on the minute boundary; requests beyond the ceiling inside a window are rejected.

## Consequences

Trivial to reason about, but clients learned to burst at the boundary: two ceilings back-to-back straddling the reset. Replaced by a boundary-free scheme.

## Category

Technical
