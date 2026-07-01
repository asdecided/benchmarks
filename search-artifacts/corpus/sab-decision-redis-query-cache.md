---
schema_version: 1
id: SAB-JC4YVMM357GG
type: decision
tags: [cache, performance]
---
# Redis Query Result Cache

## Status

Accepted

## Context

Popular dashboards re-issue identical aggregate queries many times a minute, and recomputing them dominates database load.

## Decision

A Redis cache holds aggregate query results keyed by the normalized query text, with least-recently-used eviction and a five-minute lifetime.

## Consequences

Database load drops for the hottest boards. A cached aggregate can be up to five minutes stale, which the header timestamp discloses.

## Category

Technical
