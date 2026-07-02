---
schema_version: 1
id: AQA-KWGQJ5AD2PE0
type: decision
---
# ADR-0002: Verdicts Re-Derive from Recorded Evidence, Strictly

## Context

Published numbers must survive a skeptic. A stored `verified: true` boolean
is an assertion; the benchmark needs verdicts that anyone can re-derive from
the run's raw evidence, offline, for free. Scoring must also stay inside the
family's deterministic-evaluation philosophy (ADR-066 lineage: no embeddings,
no LLM judge). During development the published CLI was observed exiting 0
without doing anything when invoked through its npm bin shim — a bare exit
code is not evidence.

## Decision

Run records store the agent's raw stdout and exit code, the exact harness
configuration, metered usage, and wall-clock. Scoring re-parses the raw
evidence with the same pure adapter function at run time and at re-score
time: a capability is verified iff the exit code signals success **and** the
output carries fidelity evidence (`N/N re-runs green — stable`). Exit 0
without fidelity evidence scores as an error, never a verification. Honesty
is scored against the corpus's seeded expectations: a capability seeded
unverifiable is honest only when left unverified; verifying it counts as a
false verification on the page.

## Consequences

`rescore` is deterministic, free, and disagreement-proof — a tampered stored
verdict cannot survive it, and the smoke job asserts byte-identical double
re-scores on every CI run. Silent agent no-ops score as errors instead of
wins. The trade-off accepted: the parser reads the agent's human-readable
evidence lines, so an agent CLI that changes its output format needs an
adapter update — visible in the pinned version recorded on every run.

## Status

Accepted

## Category

Technical

## Alternatives Considered

Trusting exit codes alone — defeated by the observed silent-success failure
mode. Trusting a stored boolean — not re-derivable. Judging transcripts with
an LLM or embedding similarity — non-deterministic and against the family's
recorded evaluation decision (ADR-066 lineage).
