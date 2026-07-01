---
schema_version: 1
id: SAB-YPYHNQ276H5A
type: decision
tags: [dashboard, realtime]
---
# WebSocket Live Dashboard Updates

## Status

Accepted

## Context

Operations teams watch boards during incidents and need figures that move as the data moves. Timer-driven re-querying wastes compute and still lags.

## Decision

The query service pushes incremental updates to open dashboards over a WebSocket streaming channel. A board subscribes to the tiles it shows and receives live deltas as new measurements arrive; realtime fanout replaces the thirty-second timer.

## Consequences

Figures move within a second of ingestion and idle boards cost nothing. The platform takes on connection management and per-tile subscription state.

## Category

Technical

## Supersedes

- SAB-G2BM261FSJ51
