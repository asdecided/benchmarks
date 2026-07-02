---
schema_version: 1
id: GRB-R5X9N01AV1E7
type: decision
tags: [benchmark, scope, relationships]
---
# GRB-ADR-0001: get-related Benchmark Scope

## Status

Accepted

## Context

`get_related`'s outgoing direction and its depth-greater-than-one
neighborhoods were unscored anywhere. The CLI surface (`rac relationships`)
exposes the typed edge map but not the MCP tool's neighborhood expansion or
the ADR-033 response budget, so a CLI-driven v1 cannot see those behaviours.

## Decision

Score what the CLI contract exposes, exactly, and record what it cannot see.
Each case declares the exact expected incoming and outgoing edge sets for one
artifact, scored as set membership over the corpus-wide
`rac relationships --json` map, gated as conformance at 1.0 with hard
negatives over both directions. Incoming-edge sources are named by inverting
the corpus map with `rac index` — plumbing that never re-ranks tool output.
Depth-greater-than-one neighborhoods and budget truncation are recorded as
the deferred MCP-stdio harness workstream, not silently dropped.

## Consequences

The outgoing direction is guarded for the first time; an edge-extraction or
inversion regression in `rac` fails CI here. The MCP-only behaviours remain
unguarded until the MCP-stdio harness lands, and that gap is written down in
the README, the family ADR, and the roadmap.

## Category

Process
