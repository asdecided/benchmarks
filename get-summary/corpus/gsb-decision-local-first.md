---
schema_version: 1
id: GSB-N4769N88GCX3
type: decision
tags: [storage]
---
# Local-First Storage

## Status

Accepted

## Context

Note-taking dies the moment saving depends on a network round-trip.

## Decision

Every edit commits to the local store first; sync reconciles in the background and never blocks input.

## Consequences

Typing latency is device-bound. Conflict resolution moves from the server to a merge policy.

## Category

Technical
