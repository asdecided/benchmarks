---
schema_version: 1
id: GRB-T58FM36EXGH1
type: requirement
tags: [deploys]
---
# One-Minute Rollback

## Status

Accepted

## Problem

When a release goes wrong, every minute of diagnosis happens in front of affected customers.

## Requirements

- [REQ-001] Operators MUST be able to trigger rollback with one action from the release view.
- [REQ-002] Rollback MUST complete within one minute at any fleet size.
- [REQ-003] Every rollback MUST record who triggered it and why.

## Success Metrics

- P95 rollback duration under sixty seconds across a quarter.

## Related Decisions

- GRB-10VE0C4C03TG
