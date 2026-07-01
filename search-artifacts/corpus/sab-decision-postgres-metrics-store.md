---
schema_version: 1
id: SAB-064J1KYRB4MR
type: decision
tags: [storage, metrics]
---
# Postgres Metrics Store

## Status

Accepted

## Context

Meridian ingests measurement series from customer sources and has to keep them queryable for years. The first datastore choice shapes every later ingestion and retention decision.

## Decision

Postgres is the primary metrics store. Measurement series land in partitioned tables keyed by source and day, and retention is enforced by dropping expired partitions.

## Consequences

One battle-tested datastore serves both metrics and application state. Partition management becomes routine operational work.

## Category

Technical
