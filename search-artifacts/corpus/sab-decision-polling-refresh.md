---
schema_version: 1
id: SAB-G2BM261FSJ51
type: decision
tags: [dashboard, refresh]
---
# Polling Dashboard Refresh

## Status

Superseded

## Context

Early boards needed periodically renewed figures without extra infrastructure. The simplest mechanism was for each open board to ask again on a timer.

## Decision

Each open board re-requests its queries on a thirty-second timer. No server-side fanout exists; the timer is the only refresh trigger.

## Consequences

Simple to operate, but every open board pays the full query cost every thirty seconds, and figures lag the source by up to the timer interval. Replaced once a server-side fanout became affordable.

## Category

Technical
