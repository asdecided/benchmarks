---
schema_version: 1
id: FDB-JPWFTJ5TD1ZE
type: decision
tags: [api, formats]
---
# JSON Response Payloads

## Status

Accepted

## Context

Every consumer built in the last three years asked for JSON first, and the XML response payloads envelope has become pure overhead for them.

## Decision

All endpoints return JSON response payloads. The legacy XML rendering remains available to existing integrations behind an explicit header until their contracts lapse.

## Consequences

New integrations start in one request. The dual rendering keeps a translation layer alive until the last XML contract lapses.

## Category

Technical

## Supersedes

- FDB-NE6YBTGZV257
