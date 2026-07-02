---
schema_version: 1
id: TALLY-0000000000R4
type: requirement
---

# Stats Reports Count, Min, Max, and Sum

## Status

Accepted

## Problem

Users summarising a series need its shape at a glance — how many values, the
extremes, and the total — in one call.

## Requirements

- [REQ-001] The tool SHALL print `count=<n> min=<a> max=<b> sum=<s>` on stdout for the numbers given to the `stats` command.
- [REQ-002] A successful `stats` invocation SHALL exit with code 0.

## Acceptance Criteria

- Running `tally.py stats 3 4 5` prints `count=3 min=3 max=5 sum=12` and
  exits 0.
