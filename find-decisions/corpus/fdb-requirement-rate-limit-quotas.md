---
schema_version: 1
id: FDB-Q4S9SC12V2GH
type: requirement
tags: [traffic]
---
# Rate Limit Quotas

## Status

Accepted

## Problem

Customers on different plans get identical throughput today, so the plan tiers have nothing to sell but support response times.

## Requirements

- [REQ-001] Each plan tier MUST define its own request ceiling per client key.
- [REQ-002] A client MUST be able to read its remaining quota from response headers.
- [REQ-003] Quota overruns MUST return the documented throttle response, never a generic error.

## Success Metrics

- Plan upgrades attributable to throughput needs become measurable.

## Related Decisions

- FDB-EW906SN9HHGN
