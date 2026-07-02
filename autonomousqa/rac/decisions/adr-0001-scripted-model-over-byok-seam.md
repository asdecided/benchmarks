---
schema_version: 1
id: AQA-KWGQJ50NF3AX
type: decision
---
# ADR-0001: The Scripted Model and Token Metering Ride the BYOK Seam

## Context

The harness must meter tokens for any agent and any provider, and CI must
exercise the full pipeline — drive, compile, fidelity gate, scoring — with no
API key and no token spend. The reference agent's published CLI reports no
token usage, offers no dry-run mode, and must not be forked or imported
(its scripted-model seam is library-only, off the published-CLI path this
benchmark is allowed to use).

## Decision

Put one local OpenAI-compatible proxy on the agent's documented BYOK seam
(`OPENAI_BASE_URL`) and give it two modes: **forward**, which relays to the
operator's real provider and records the `usage` block of every response;
and **scripted**, which replays a canned per-capability tool-call flow
(`apps/<app>/flows/<capability>.json`) and reports deterministic estimated
usage. CI's smoke job and the fixture sweep run scripted; benchmark results
run forward.

## Consequences

Token counts are measured by the harness, uniformly, for every agent that
speaks the OpenAI-compatible wire format — not self-reported. The whole
pipeline is CI-testable for free, and scripted flows double as proof that
every capability seeded verifiable genuinely is. The trade-offs accepted:
scripted usage numbers are estimates (flagged `estimated` and excluded from
benchmark claims), and providers reachable only through non-OpenAI-compatible
adapters are metered only if routed through a compatible gateway.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

Parsing token counts from agent output — the published CLI prints none, and
self-reporting would vary per agent. Importing the agent's library seam for
a scripted ModelClient — crosses the published-contract boundary (ADR-092/
ADR-063 lineage). Counting tokens with a local tokenizer — approximates what
providers bill and adds a dependency that can drift.
