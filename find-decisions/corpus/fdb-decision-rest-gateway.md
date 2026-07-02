---
schema_version: 1
id: FDB-7KPZDW2SNEK1
type: decision
tags: [api, gateway]
---
# REST Public Gateway

## Status

Accepted

## Context

Partner integrations need one stable public entry point with uniform authentication, limits, and versioning.

## Decision

The public API gateway exposes versioned REST resource endpoints for partner integrations. All public traffic enters here and nowhere else.

## Consequences

Partners integrate against one predictable surface. Composite screens pay multiple fetches, which keeps the pressure for a query-language surface alive.

## Category

Technical
