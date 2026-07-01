---
schema_version: 1
id: GRB-4D11EAG0GAB9
type: decision
tags: [deploys]
---
# Blue-Green Deployments

## Status

Accepted

## Context

Releases used to overwrite the running fleet in place, so a bad release and its rollback both meant downtime.

## Decision

Every release deploys to an idle colour, passes its smoke suite there, and then shifts traffic atomically. The previous colour stays warm for instant rollback.

## Consequences

Rollback becomes a traffic shift, not a redeploy. The fleet costs double capacity during the overlap window.

## Category

Technical

## Supersedes

- GRB-2WGZ1JPH4SGA
