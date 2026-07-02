---
schema_version: 1
id: SAB-09EB0V23GH85
type: roadmap
tags: [realtime]
---
# Realtime Analytics

## Status

Planned

## Context

Incident-response teams want boards that move with the data. The realtime programme replaces timer-driven refresh with pushed deltas end to end.

## Outcomes

- Open boards update within a second of ingestion.
- Idle boards consume no query compute.

## Initiatives

- Ship the WebSocket delta channel.
- Ship per-tile subscriptions and backpressure.
- Retire the legacy refresh timer.

## Success Measures

- P95 ingestion-to-pixel latency under one second on the incident board.

## Related Decisions

- SAB-YPYHNQ276H5A
