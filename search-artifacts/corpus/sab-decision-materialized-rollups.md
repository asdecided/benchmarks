---
schema_version: 1
id: SAB-3G8GBMG2QWTF
type: decision
tags: [storage, performance]
---
# Materialized Rollup Tables

## Status

Accepted

## Context

Long-range charts aggregate months of raw measurements, which is too slow to compute per view.

## Decision

Hourly and daily rollup tables are materialized at ingestion time; charts beyond a two-day window read rollups instead of raw series.

## Consequences

Long-range charts render in constant time. Rollups add ingestion-side compute and a reconciliation job for late-arriving data.

## Category

Technical
