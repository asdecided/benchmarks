---
schema_version: 1
id: GSB-ME7EY2ZE6KSQ
type: requirement
tags: [capture]
---
# Instant Capture

## Status

Accepted

## Problem

A thought not captured in five seconds is lost to the meeting it interrupted.

## Requirements

- [REQ-001] A new note MUST accept typed input within five hundred milliseconds of the capture shortcut, from any state including cold start.
- [REQ-002] Capture MUST work with no network.
- [REQ-003] A capture MUST land in the inbox without asking where to file it.

## Success Metrics

- P95 shortcut-to-typing latency under half a second on reference hardware.

## Related Decisions

- GSB-N4769N88GCX3
