---
schema_version: 1
id: GCB-KWRRD0T8K2Z9
type: decision
tags: [benchmark, outcomes, resolution, publication]
---
# GCB-ADR-0002: The Evidence Run Is SWE-DecisionBench's Resolution Co-Primary

## Status

Accepted

## Context

The SWE-DecisionBench publication study (rac-core
`rac-grounding-baseline-study`, REQ-002/003) requires an executable,
decision-conditioned resolution outcome alongside structural
decision-adherence — real or version-conditioned tasks whose correct patch
depends on a recorded governing decision, scored by upstream tests. That is
exactly this member's shape (GCB-ADR-0001): version-pin decisions among
deterministic distractors, prompts that never restate the pinned version, and
the upstream harness's executable tests as the only scorer.

## Decision

The GitChameleon evidence run's per-arm upstream pass rate is published as
**SWE-DecisionBench's second co-primary outcome, "decision-conditioned
resolution"** (mirror decision: `../decisiongrounding/rac/decisions/
co-primary-outcomes.md`). Operationally:

- The run pipeline gains `solutions` / `score` / `stats` seams so one funded
  session can produce per-(example, arm) paired records
  (`schema/resolution_record.schema.json`) and the pre-registered paired
  analysis (exact McNemar, effect sizes) with `passed` as the outcome.
- We still add **no scorer**: `score` only normalizes the upstream harness's
  per-example pass/fail output into paired records.
- GCB-ADR-0001's boundaries are restated, not relaxed: this is an **evidence
  run, never a CI merge gate**; results are labelled with the protocol
  (no-version-in-prompt) and are **not comparable to the upstream
  leaderboard**; an unfavourable delta is published plainly.
- The falsifier for this outcome is pre-registered in
  `../decisiongrounding/spec/analysis-plan-amendment-1.md` (H2).

## Consequences

- The SWE- family name is earned with executable verification; the funded run
  now covers two benchmarks and its handoff budgets both.
- The paired analysis code lives in `decisiongrounding/scoring/stats.py` and
  is imported across members at the repo root — the members share statistics,
  not identity (rac-core ADR-092).

## Category

Product

## Alternatives Considered

- **A separate publication for the GitChameleon result.** Rejected: the study
  needs both outcomes in one place; a second paper would dilute both.
- **Re-scoring solutions with our own harness.** Rejected: duplicates the
  upstream executable verdict with a less credible one (GCB-ADR-0001).

## Related Decisions

- GCB-329CD3DAMG8Y
