---
schema_version: 1
id: FDB-KVYVX53ZT01B
type: design
tags: [auth, sessions]
---
# Session Refresh Flow

## Status

Accepted

## Context

Stateless JWT sessions expire quickly by design, and clients must renew them without interrupting the person using the app.

## User Need

A signed-in user should never see a sign-in wall while actively using a client that holds a valid refresh grant.

## Design

Clients renew the JWT in the background when two-thirds of its lifetime has elapsed. The refresh call rotates the grant, and a failed rotation retries once before surfacing re-authentication.

## Constraints

Renewal must tolerate one gateway clock-skew interval; overlapping renewals from concurrent tabs must collapse to one rotation.

## Rationale

Proactive renewal at two-thirds lifetime absorbs transient failures inside the remaining validity window.

## Related Decisions

- FDB-FNC5AS3XS0FE
