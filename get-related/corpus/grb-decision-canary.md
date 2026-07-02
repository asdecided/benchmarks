---
schema_version: 1
id: GRB-10VE0C4C03TG
type: decision
tags: [deploys]
---
# Canary Releases

## Status

Accepted

## Context

Some regressions only appear under real traffic patterns that the smoke suite cannot simulate.

## Decision

High-risk changes route a small percentage of live traffic to the new colour first and compare error and latency baselines before the full shift.

## Consequences

Real-traffic regressions surface on a sliver of users. The compare window adds minutes to high-risk releases only.

## Category

Technical

## Related Decisions

- GRB-4D11EAG0GAB9
