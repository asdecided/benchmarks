---
schema_version: 1
id: GCB-7M4VX2QK9D6H
type: decision
tags: [benchmark, execution, models, provenance]
---
# GCB-ADR-0003: Pin and Checkpoint the Funded Evidence Run

## Status

Accepted

## Context

The GitChameleon evidence run makes 328 answering calls per arm and must
survive rate limits, transient provider failures, and operator interruption
without silently changing models or duplicating spend. GCB-ADR-0001 requires
a strong embedding baseline over the same corpus as As Decided, while
GCB-ADR-0002 requires paired, provenance-bearing resolution records.

## Decision

Pin the held-constant answering model to `claude-opus-4-8` and the naive RAG
embedder to `voyage-4-large`. Voyage receives the exact decision artifacts
with `input_type=document` and the shared `<library> version pin` query with
`input_type=query`; cosine similarity ranks the top three artifacts, with
path order breaking exact ties. Truncation is disabled so an over-limit input
fails rather than changing an arm invisibly.

Answer generation is checkpointed per arm. Existing output is never
overwritten implicitly: a caller must select `--resume` or `--overwrite`.
Resume skips completed example IDs, flushes every new JSONL record, and stores
SHA-256 hashes of the exact task prompt and grounding list. Provider calls
retry only rate limits, connection failures, and server errors with bounded
backoff. A funded run begins with `--limit 1` for every arm before the full
call set is authorized.

The upstream GitChameleon commit remains a separate, mandatory scoring pin.
Neither an answering completion nor a locally normalized record is a pass;
only the upstream executable harness supplies that verdict.

The concrete frozen values live in `../run-config.json`. The first registered
run uses dataset commit `799a6a33e572a07a8985914e7251f5dea54b0ac4`
(328 raw JSONL rows) and upstream harness commit
`3a1b6045a6b2a276bd24d715589cb041f8eccb93`. The scorer image is built locally
from that checkout; the upstream floating `latest` image is not evidence.

## Consequences

Interrupted runs can continue without duplicate calls, the three arms remain
auditable at the injection boundary, and the naive RAG label names a concrete
strong baseline. The evidence run still requires two owner-supplied provider
credentials and an upstream scoring environment. No result exists until all
three arm files are scored and the paired records pass completeness checks.

## Category

Process

## Related Decisions

- GCB-329CD3DAMG8Y
- GCB-KWRRD0T8K2Z9
