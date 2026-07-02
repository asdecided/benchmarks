---
schema_version: 1
id: SAB-V2MYF3VJZDVF
type: decision
tags: [benchmark, scope, ranking]
---
# SAB-ADR-0001: search-artifacts Benchmark Scope

## Status

Accepted

## Context

`search_artifacts` is the general retrieval surface, and its earlier coverage
(rac-core's in-repo `rac eval`) gates only P@1 and R@5 over a 12-artifact
corpus with a top-5 hard-negative window. That gate is blind to ordering
within ranks 2–5 — ironic, since the shipped BM25+RRF ranking change was
justified by within-window ordering — and blind to a hard negative at rank 6,
which the full match list still delivers to agents.

## Decision

This benchmark scores the same surface at more realistic scale: 30 artifacts
across all five types, six query categories with four cases each, MRR gated
alongside P@k / R@k, and hard negatives judged against the full returned
list. Matching is AND-over-query-tokens with token-boundary prefixes, so
supersession hard negatives are authored to share no token (or prefix) with
their query.

## Consequences

Within-top-5 ordering regressions and full-list negative leaks now fail CI.
The corpus is larger to author and its vocabulary partitioning is
load-bearing: edits to fixture text must re-run the benchmark before commit.

## Category

Process
