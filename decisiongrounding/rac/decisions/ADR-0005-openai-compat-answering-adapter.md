---
schema_version: 1
id: DG-KWGPQK7M7RVQ
type: decision
tags: [harness, answering-model, gateway, methodology]
---

# ADR-0005: OpenAI-Compatible Answering Adapter Preserves the Held-Constant Contract

## Status

Accepted

## Category

Technical

## Context

ADR-0001 fixes the benchmark's single-variable design: every arm feeds its
grounding into the SAME answering model behind the SAME scaffold, and scoring
is deterministic — structured output parsed by schema, never free-text
interpretation. Until now the only real backend was Anthropic-native
(`--answering claude`: the `anthropic` SDK, `output_config` structured
outputs, optional Batch API). That covers LiteLLM gateways in Anthropic
passthrough mode, because the SDK honours `ANTHROPIC_BASE_URL`.

Enterprise adopters commonly route ALL model traffic through a LiteLLM
gateway that exposes only the OpenAI-compatible `/chat/completions` surface.
For them the native backend cannot connect at all, which makes the benchmark
unrunnable exactly where the rac-grounding thesis is being evaluated for
adoption. The temptation under that pressure — parse free-form text, or let a
second adapter drift its prompt — would quietly break the held-constant
contract and the determinism rule.

## Decision

Add one OpenAI-compatible answering backend, factory spec
`litellm:<model-alias>`, bound by adapter-equivalence rules:

- **Shared semantics, different wire.** The adapter consumes the same
  module-level helpers as the Claude backend — one user-prompt builder, one
  `_PROPOSED_CHANGE_SCHEMA`, the same scaffold as the system message, the
  same JSON field checks — so the two adapters cannot drift. Only the
  envelope differs: OpenAI `response_format: {type: json_schema, strict}`
  instead of Anthropic `output_config`.
- **Structured output is required, never approximated.** A non-JSON reply
  raises; there is no free-text fallback. `finish_reason: content_filter`
  maps to the same refused `ProposedChange` the Claude backend produces.
- **Usage is normalised** (`prompt_tokens`/`completion_tokens` →
  `input_tokens`/`output_tokens`) so cost reporting is backend-agnostic.
- **Version honesty.** `answering_model.version` records the full spec
  string (`litellm:<alias>`) — a gateway alias, not a first-party pin. Runs
  are reproducible only if the alias is pinned to a fixed model on the
  gateway; the probe and docs say so explicitly.
- **Synchronous only.** The Batch API is not part of the OpenAI surface;
  `--batch` and `run_real.sh BATCH=1` refuse the combination loudly.
- **Stdlib transport.** `urllib.request` — no new dependency in the spine.

`scripts/litellm_probe.py --mode openai` probes the exact adapter request so
a gateway is validated before any funded spend, mirroring the native probe.

## Consequences

### Positive

- The benchmark runs through both LiteLLM surfaces, so enterprise evaluation
  no longer depends on how a gateway happens to be configured.
- The shared-helper structure makes adapter drift a code-review-visible
  change rather than a silent divergence.
- Future per-provider adapters (the publish roadmap's multi-model
  initiative) have a settled equivalence contract to follow.

### Negative

- A second wire format to maintain, and gateway translation of
  `response_format` varies by backing model — the probe is now a required
  step, not a courtesy.

### Risks

- **Alias drift.** A gateway alias silently re-pointed at a new model
  invalidates comparability while the recorded version stays the same
  string. Mitigation: version records the spec string (honest about being an
  alias), and probe/docs require pinning the alias before a recorded run.

## Alternatives Considered

#### Depend on the `openai` client library

Familiar, but adds a dependency for one POST endpoint and another surface to
pin. Rejected: stdlib `urllib` keeps the spine dependency-free.

#### Free-text JSON extraction when structured output is unavailable

Would run on more gateways. Rejected outright: scoring must stay
deterministic (ADR-0001); a lenient parser is a silent scoring change.

#### Require Anthropic passthrough configuration

Pushes a gateway reconfiguration onto the adopter's platform team before any
evaluation can happen. Rejected: the benchmark should meet the common
enterprise configuration where it is.

## Related Decisions

- DG-KVMRSS0C7T4M

## Success Measures

A run through an OpenAI-compatible gateway produces a report whose scoring
path, prompts, and schema are byte-identical to a native-backend run's, with
the backend visible only in `answering_model.version` and transport metadata.

## Review Date

When a second non-Anthropic answering adapter is added, or after the first
real gateway-routed funded run — whichever comes first.
