---
schema_version: 1
id: SAB-XRTP8KP80P17
type: requirement
tags: [alerting]
---
# Alert Notifications

## Status

Accepted

## Problem

Teams find out about threshold breaches by looking at a board, which means nights and weekends go unwatched.

## Requirements

- [REQ-001] Users MUST be able to attach a threshold alert to any numeric tile.
- [REQ-002] A firing alert MUST notify the chosen destinations within sixty seconds of the breaching measurement.
- [REQ-003] Notifications MUST deduplicate so a flapping series produces at most one notification per quiet period.

## Success Metrics

- Median breach-to-notification latency under thirty seconds.
- Alert fatigue survey score improves quarter over quarter.
