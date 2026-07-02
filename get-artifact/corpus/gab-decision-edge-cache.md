---
schema_version: 1
id: GAB-P3AM5CX0C6AM
type: decision
tags: [performance]
---
# Edge Cache Strategy

## Status

Accepted

## Context

Atlas pages are read worldwide but written from one region, and read latency dominates perceived quality.

## Decision

Rendered pages are cached at the edge with a five-minute lifetime and purged on publish, so a page is never more than one publish behind.

## Consequences

Reads are served near the reader. Publish acquires a purge step that must succeed before the editor reports success.

## Category

Technical
