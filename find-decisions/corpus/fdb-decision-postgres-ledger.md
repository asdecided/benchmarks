---
schema_version: 1
id: FDB-0R2J9511KJFP
type: decision
tags: [billing, storage]
---
# Postgres Billing Ledger

## Status

Accepted

## Context

Usage-based billing needs an append-only record of every metered event that finance can audit line by line.

## Decision

Metered events append to a Postgres billing ledger table with no updates and no deletes; corrections are compensating entries.

## Consequences

Every invoice reconciles to ledger rows. Ledger growth is bounded by monthly partition archival.

## Category

Technical
