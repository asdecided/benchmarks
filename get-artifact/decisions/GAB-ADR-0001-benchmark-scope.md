---
schema_version: 1
id: GAB-VD85EQATX6AM
type: decision
tags: [benchmark, scope, resolution]
---
# GAB-ADR-0001: get-artifact Benchmark Scope

## Status

Accepted

## Context

`get_artifact` is a contract-shaped tool: for a given lookup there is exactly
one correct outcome — resolved with the stable payload fields, a duplicate
error naming every path, or a not-found error. Ranked-retrieval metrics do
not describe it; a pass rate does.

## Decision

The benchmark drives `rac resolve <id> corpus/ --json` and scores
**conformance pass-rate, gated at 1.0 with zero tolerance**, per the
benchmark family contract (rac-core ADR-097). Cases cover exact-id,
case-insensitive, and legacy-alias hits, the duplicate error shape (backed by
a committed duplicate pair in the fixture corpus), and the not-found error
shape, asserting outcome, exit code, and the ADR-007 stable payload fields.

## Consequences

Any change to the resolve contract — a renamed field, a silently resolved
duplicate, a changed exit code — fails CI here. Provenance-field conformance
is deferred to the MCP-stdio harness workstream because the current CLI
payload does not carry provenance enrichment; the deferral is recorded in the
README and the `tool-benchmarks` roadmap rather than silently dropped.

## Category

Process
