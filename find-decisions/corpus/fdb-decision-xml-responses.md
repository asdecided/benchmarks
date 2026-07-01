---
schema_version: 1
id: FDB-NE6YBTGZV257
type: decision
tags: [api, formats]
---
# XML Response Payloads

## Status

Deprecated

## Context

Beacon's earliest integrators were enterprise systems whose tooling consumed XML natively.

## Decision

All public endpoints return XML response payloads; content negotiation is not offered.

## Consequences

Fit the first integrators, but every new consumer since has asked for something lighter, and the envelope carries heavy namespace boilerplate. Deprecated for new endpoints.

## Category

Technical
