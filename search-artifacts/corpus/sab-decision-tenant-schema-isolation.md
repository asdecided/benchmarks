---
schema_version: 1
id: SAB-TQDNAG5W1PZM
type: decision
tags: [multitenancy, storage]
---
# Per-Tenant Schema Isolation

## Status

Accepted

## Context

Customer datasets must never bleed into one another, and noisy neighbours must not degrade other customers' queries.

## Decision

Each tenant gets its own database schema. Every query path is scoped to the tenant schema by construction; cross-schema access requires an explicit support-role grant.

## Consequences

Isolation failures become structurally impossible in the common path. Schema migrations fan out per tenant and take longer to roll through.

## Category

Technical
