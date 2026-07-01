---
schema_version: 1
id: GSB-SRGSB5PWQRM9
type: design
tags: [structure]
---
# Graph View

## Status

Accepted

## Context

Linked notes form a web nobody can see, and the web is the point.

## User Need

A writer wants to see a note's neighbourhood to rediscover related thinking.

## Design

A local graph pane on each note renders two hops of links with the current note centred. Nodes scale by link count; clicking recentres.

## Constraints

The pane renders from the local link table only; it must never wait on sync.

## Rationale

Two hops is the neighbourhood a person can actually read; a whole-corpus hairball demos well and informs nobody.

## Related Requirements

- GSB-F9W84J79HAV6
