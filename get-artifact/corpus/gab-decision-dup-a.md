---
schema_version: 1
id: GAB-YP0MNBY0KN43
type: decision
tags: [storage]
---
# Attachment Storage (Original)

## Status

Accepted

## Context

Page attachments need durable storage with direct-link serving.

## Decision

Attachments are stored in the object store under content-hash keys and served by signed direct links.

## Consequences

Uploads deduplicate by content. Link expiry must be tuned to reader session length.

## Category

Technical
