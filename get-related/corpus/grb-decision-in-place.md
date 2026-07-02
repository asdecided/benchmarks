---
schema_version: 1
id: GRB-2WGZ1JPH4SGA
type: decision
tags: [deploys]
---
# In-Place Upgrades

## Status

Superseded

## Context

The first fleet was three machines; anything more elaborate than replacing binaries on them was overkill.

## Decision

Releases stop the service, replace the binary on each machine in sequence, and start it again.

## Consequences

Simple while the fleet was tiny, but every release carried downtime equal to the restart, and rollback repeated it. Replaced by a colour-switched scheme.

## Category

Technical
