---
schema_version: 1
id: FDB-3AJ2WDMA3CEM
type: decision
tags: [benchmark, scope, supersession]
---
# FDB-ADR-0001: find-decisions Benchmark Scope

## Status

Accepted

## Context

`find_decisions` is the one Lore retrieval tool with a structural liveness
defense, and until this suite it had zero benchmark coverage: supersession was
tested only through `search_artifacts`, which applies no liveness filter. The
claim that matters — "a retired decision never reaches the agent from this
surface" — needs its own corpus, where the retired decision is deliberately
the lexically best match.

## Decision

The benchmark drives `rac find <query> corpus/ --decisions --json` (the same
live-decision service the MCP tool serves) against a corpus whose supersession
chains put the strongest query vocabulary on the *superseded* members. Hard
negatives are judged against the full returned list, and
`negative_violations == 0` is always gated. Scoring is P@k / R@k / MRR,
macro-averaged, per the benchmark family contract (rac-core ADR-097 extending
ADR-066).

## Consequences

A ranking or filter change in `rac` that lets a superseded, deprecated,
proposed, or non-decision artifact surface from this tool fails CI here, at
any rank. The corpus vocabulary must stay deliberately partitioned: a query
token leaking into a hard-negative artifact turns a structural test into a
lexical accident, so corpus edits must re-run the benchmark before commit.

## Category

Process
