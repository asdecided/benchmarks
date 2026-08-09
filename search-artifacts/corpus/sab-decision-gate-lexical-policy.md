---
schema_version: 1
id: SAB-6A7E1EC1CA11
type: decision
tags: [archive, lifecycle]
---
# Archive Retention Lifecycle Expiry Policy

## Status

Accepted

## Context

Customer exports need one authoritative archive retention lifecycle and expiry
policy. Search must prefer this focused decision over broadly connected index
records that merely mention the same vocabulary.

## Decision

Use the archive retention lifecycle defined here. Archive data moves to cold
storage after thirty days, retention lasts seven years, and expiry deletes the
object and its encryption key together.

## Consequences

The focused policy is the primary lexical answer for archive, retention,
lifecycle, and expiry queries.

## Category

Technical
