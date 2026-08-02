---
schema_version: 1
id: GCB-329CD3DAMG8Y
type: decision
tags: [benchmark, scope, external, versions]
---
# GCB-ADR-0001: GitChameleon Evidence-Run Scope

## Status

Accepted

## Context

GitChameleon 2.0 (arXiv:2507.12367; 328 version-conditioned Python problems
with executable unit tests) is the external benchmark whose task — write code
against the pinned library version, not the version the model remembers — is
Lore's supersession thesis in code form. Its execution-based scoring is
deterministic, which no other recognized external candidate offers. Upstream
code is Apache-2.0; the dataset (`cabbage972/GitChameleon-2.0`) is MIT.

## Decision

Adopt GitChameleon as an **evidence run**, never a merge gate: scoring belongs
to the upstream harness (executable tests), results are labelled with the
upstream dataset revision, and nothing here enters CI's gated path
(rac-core ADR-066/ADR-097 boundary; `external-benchmark-evidence` roadmap).

The arm design reuses the DG-ADR-0001 single-variable pattern: a
held-constant answering model; arms differ only in grounding. The governing
knowledge is modelled as what it really is in a codebase — a **version-pin
decision** — one RAC decision artifact per example, placed among
deterministic distractor pins from other examples. The task prompt states the
problem but NOT the pinned version: version awareness must arrive through the
arm's grounding (or the model's weights), because supplying the pin in every
prompt would measure prompt engineering, not grounding.

The dataset is fetched on demand (stdlib script, provenance and content hash
recorded), never vendored; three verbatim rows are committed as MIT-licensed
test fixtures with attribution. The funded-run baseline is pinned by
GCB-ADR-0003 to Voyage `voyage-4-large`; it ranks the same Markdown artifacts
with explicit query/document embedding modes and deterministic cosine ties.

## Consequences

The product-backed arm is named `asdecided` in CLI arguments, generated files,
records, and published results. The former `rac` label is not an accepted alias:
mixing both names would make paired-run completeness ambiguous and retain a
retired product name in durable evidence.

Grounding quality becomes the only manipulated variable, so an asdecided-vs-
no-grounding delta on the upstream pass rate is attributable to retrieval of
the governing pin. The deliberate cost: our numbers are **not comparable to
the upstream leaderboard**, which conditions the prompt on the version
explicitly — every published result must say so. The naive_rag arm refuses
without the pinned embedder's API key, so a weak lexical stand-in can never
masquerade as the RAG baseline.

## Category

Process
