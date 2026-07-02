---
schema_version: 1
id: GRB-65C1EA6PXMR7
type: requirement
tags: [deploys]
---
# Zero-Downtime Releases

## Status

Accepted

## Problem

Customers in every timezone see the maintenance window; there is no quiet hour left to hide a restart in.

## Requirements

- [REQ-001] A routine release MUST NOT drop or refuse any in-flight request.
- [REQ-002] Rollback MUST restore the previous behaviour within one minute of the decision.
- [REQ-003] Release and rollback MUST be exercised by the pipeline on every change, not only on release days.

## Success Metrics

- Releases stop appearing in the customer-facing status history.

## Related Decisions

- GRB-4D11EAG0GAB9
