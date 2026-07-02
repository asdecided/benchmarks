---
schema_version: 1
id: AQA-KWGQJ4B7MDRK
type: requirement
---
# AutonomousQA Benchmark Member

## Status

Accepted

## Problem

"Better than DROID" is a claim until anyone can re-run it. The Lore family
needs a public, deterministic benchmark for autonomous-QA agents — a property
of frozen sample apps, seeded corpora, and evidence-based scoring, not of any
one agent — so verified-capability rate, honesty on ambiguous criteria, token
cost, and wall-clock become reproducible arguments. The intent is recorded in
the engine family's qa-benchmark roadmap; this member implements it inside
rac-benchmarks per the repository-topology decision (ADR-092 lineage).

## Requirements

- [REQ-001] The member SHALL ship at least three frozen sample apps spanning the drive modalities browser flow, API service, CLI tool, and browser extension, each served with no dependencies that can drift.
- [REQ-002] Each sample app SHALL seed a Lore corpus that validates clean under `rac validate`, with acceptance criteria of graded difficulty including negative paths and deliberately ambiguous capabilities whose honest outcome is unverified.
- [REQ-003] The harness SHALL take (sample app, corpus, agent config), run the agent per capability over its published CLI, and emit machine-readable records carrying verified/unverified per capability, fidelity pass-rates, tokens in and out, and wall-clock.
- [REQ-004] Recorded results SHALL re-score deterministically offline, without re-running any agent or re-spending any token.
- [REQ-005] The agent invocation SHALL be a pluggable seam so a second autonomous-QA agent can be measured by adding one adapter.
- [REQ-006] The member SHALL consume the corpus only through `rac export --graph` and the reference agent only through its published npm CLI, never repo internals.
- [REQ-007] The results page SHALL be generated from harness records and report rates by app, by modality, and by model, with the exact harness configuration per published result and stated run-to-run variance.
- [REQ-008] CI SHALL run a smoke-scale job — one cheap capability against one app with a scripted model — so the harness cannot rot without keys or token spend.

## Success Metrics

A third party can clone the member, set one API key, and reproduce the
published numbers within the run-to-run variance the page itself states; the
scripted smoke job stays green on every change; and every capability seeded
verifiable is proven verifiable by a scripted flow through the real pipeline.

## Risks

Overfitting the reference agent's drive to the benchmark apps — mitigated by
freezing apps on publication and landing new behaviour as new apps. Provider
disputes over cross-model comparisons — mitigated by publishing the exact
harness config per result and keeping scoring deterministic and re-runnable.

## Assumptions

Small seeded apps are representative enough to measure the agent loop, and
publishing honest unverified rates is a credibility feature. The published
Proofkeeper CLI remains consumable as pinned in the workspace; a version bump
is a visible config change, never a silent drift.

## Related Designs

- AQA-KWGQJ4PHZE3H

## Related Decisions

- AQA-KWGQJ50NF3AX
- AQA-KWGQJ5AD2PE0
