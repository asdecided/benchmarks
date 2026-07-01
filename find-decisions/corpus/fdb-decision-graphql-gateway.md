---
schema_version: 1
id: FDB-Q1JSNEV4Y0JB
type: decision
tags: [api, gateway]
---
# GraphQL Public Gateway

## Status

Proposed

## Context

Some consumers stitch many resource fetches per screen and ask for a query language over the public surface.

## Decision

Expose a GraphQL endpoint alongside the resource endpoints, fed by the same authorization layer.

## Consequences

Would collapse fetch chains for composite screens, at the cost of a second public contract to version and secure. Not yet accepted; the resolver cost model is unproven.

## Category

Technical
