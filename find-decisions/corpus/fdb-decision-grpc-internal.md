---
schema_version: 1
id: FDB-CCSDA8JGFTTP
type: decision
tags: [services]
---
# gRPC for Internal Services

## Status

Accepted

## Context

Internal service calls were ad hoc HTTP with hand-rolled clients, and interface drift between teams caused two outages.

## Decision

Internal service-to-service calls use gRPC with contracts generated from committed proto definitions; clients are generated, never hand-written.

## Consequences

Interface drift is caught at build time. The browser edge still terminates plain HTTP; gRPC is internal only.

## Category

Technical
