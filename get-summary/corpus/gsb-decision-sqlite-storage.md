---
schema_version: 1
id: GSB-ZS9ZFZ65FJK8
type: decision
tags: [storage]
---
# SQLite Local Store

## Status

Accepted

## Context

The local store must survive crashes mid-write on every platform the app ships to.

## Decision

The device store is a single SQLite database in WAL mode; notes, links, and the search index live in one transactional file.

## Consequences

Crash consistency comes from a battle-tested engine. The whole corpus is one file to back up and one file to corrupt — hence checkpointed snapshots.

## Category

Technical
