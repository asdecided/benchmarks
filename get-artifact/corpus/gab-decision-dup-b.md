---
schema_version: 1
id: GAB-YP0MNBY0KN43
type: decision
tags: [storage]
---
# Attachment Storage (Duplicate)

## Status

Accepted

## Context

A migration rehearsal copied this record without re-keying its identity, leaving two files that answer to one id.

## Decision

This duplicated file exists so the benchmark can assert the resolver reports a duplicate rather than silently picking a file.

## Consequences

Exact-id resolution over this corpus must fail loudly for this id.

## Category

Technical
