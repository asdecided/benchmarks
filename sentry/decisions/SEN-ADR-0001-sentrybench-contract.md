---
schema_version: 1
id: SEN-A1B2C3D4E5F6
type: decision
tags: [benchmark, sentry, enforcement]
---
# SEN-ADR-0001: SentryBench Correctness Contract

## Status

Accepted

## Context

Sentry is a deterministic enforcement surface, not a retrieval system. A useful
evaluation must prove that known violations are blocked, compliant and
unrelated changes remain green, findings cite the correct decision and rule,
and the dedicated and composed gate surfaces do not drift.

A single blended coverage percentage would obscure two different questions:
whether enforcement is correct where rules exist, and how much of a corpus has
been classified for enforcement.

## Decision

SentryBench is a contract-shaped benchmark consumed through the published
`decided` executable only.

1. Correctness cases are deterministic, offline, and gated at 1.0 with zero
   tolerance.
2. Every enforceable rule family has both `must_block` and `must_allow`
   examples.
3. Diff cases distinguish newly introduced violations from pre-existing,
   removed, adjacent, and unrelated code.
4. Findings are scored by code, governing decision, rule ID, path, and line
   when the engine provides one.
5. SARIF accuracy, `decided sentry` / `decided gate --code` parity over their
   shared public finding projection, and byte-identical repeated JSON are
   first-class cases. Sentry-specific decision/rule provenance is scored on
   the dedicated JSON surface until the composed gate exposes equivalent
   fields.
6. Corpus adoption and eligible enforcement coverage remain diagnostic
   metadata and are never collapsed into correctness.
7. Wall-clock performance is a separate, non-scored mode. Correctness metrics
   contain no clock, network, randomness, embedding, or model output.

## Consequences

The benchmark can block a semantic enforcement regression without importing
Core internals or using an LLM judge. Fixture expansion is additive. Timing
results can guide performance work but cannot make an unchanged correctness run
non-deterministic. Gate-level decision and rule provenance remains an explicit
follow-up rather than an inferred capability.

## Related Requirements

- sentrybench-deterministic-enforcement-evaluation

## Category

Process
