---
schema_version: 1
id: GSB-8PW67GGPHT7R
type: decision
tags: [security]
---
# End-to-End Encryption

## Status

Accepted

## Context

Private notes carry the most sensitive text people write, and server operators should be structurally unable to read them.

## Decision

Note content is encrypted on device with keys the server never holds; the server syncs opaque blobs.

## Consequences

A subpoena or a breach yields ciphertext. Server-side search becomes impossible and search must run on device.

## Category

Technical
