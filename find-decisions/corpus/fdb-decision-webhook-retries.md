---
schema_version: 1
id: FDB-1KDR4AFPQ2GK
type: decision
tags: [delivery]
---
# Exponential Webhook Retries

## Status

Accepted

## Context

Consumer endpoints flap, and a single delivery attempt was silently dropping events during consumer deploys.

## Decision

Failed webhook deliveries retry on an exponential backoff schedule with jitter for up to twenty-four hours, then land in a replayable dead-letter queue.

## Consequences

Consumers stop losing events to their own deploys. Duplicate delivery becomes possible and consumers must deduplicate on event id.

## Category

Technical
