---
schema_version: 1
id: GSB-75BSP552T8R0
type: decision
tags: [benchmark, scope, portfolio]
---
# GSB-ADR-0001: get-summary Benchmark Scope

## Status

Accepted

## Context

`get_summary` grounds an agent's first look at a corpus: the artifact counts
by type and the health shape. A wrong count silently mis-frames every later
retrieval, and the payload's byte stability is what lets its consumers cache
and diff it.

## Decision

The benchmark drives `rac portfolio <root> --json` against fixtures of known
composition and scores conformance gated at 1.0: exact totals and by-type
counts across all five artifact types, the empty-corpus shape against a
committed empty fixture, and byte stability across consecutive runs on both
fixtures.

## Consequences

A counting, classification, or serialization-order regression in the
portfolio service fails CI here. The fixture composition is load-bearing:
adding a file to the corpus must update the `counts` expectations in the same
change.

## Category

Process
