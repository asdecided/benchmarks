---
schema_version: 1
id: SEN-D4E5F6G7H8J9
type: decision
tags: [fixture, coverage]
---
# Decision: Product Voice Requires Human Review

## Status

Accepted

## Context

Product voice cannot be reduced to a deterministic source check.

## Decision

Keep product-voice review human.

## Consequences

Sentry reports the decision as classified but ineligible.

## Code Constraints

```yaml
version: 1
eligibility: ineligible
reason: "Product voice requires human judgement."
```

## Category

Product
