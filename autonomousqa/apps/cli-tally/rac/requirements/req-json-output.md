---
schema_version: 1
id: TALLY-0000000000R5
type: requirement
---

# JSON Output Is Machine-Parseable

## Status

Accepted

## Problem

Pipelines consume tally's output programmatically; the `--json` flag must
produce a stable one-line JSON object. Verifying this takes chained checks —
the flag, the exact serialization, and the exit code together.

## Requirements

- [REQ-001] The tool SHALL, when `--json` is given, print the command's result as a single-line JSON object on stdout.
- [REQ-002] The JSON form of `stats` SHALL carry the keys `count`, `min`, `max`, and `sum` with integer values.

## Acceptance Criteria

- Running `tally.py stats --json 3 4 5` prints exactly
  `{"count": 3, "min": 3, "max": 5, "sum": 12}` and exits 0.
