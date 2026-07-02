---
schema_version: 1
id: FDB-EW906SN9HHGN
type: decision
tags: [traffic]
---
# Sliding Window Rate Limits

## Status

Accepted

## Context

Boundary bursts let clients double their effective ceiling under the fixed window rate limits scheme.

## Decision

The limiter weighs the previous and current minute proportionally, sliding continuously, so no reset boundary exists to straddle.

## Consequences

Burst-at-the-boundary disappears and observed throughput matches the documented ceiling. The counter costs one extra read per decision.

## Category

Technical

## Supersedes

- FDB-Q1G6QMGGX897

## Related Requirements

- FDB-Q4S9SC12V2GH
