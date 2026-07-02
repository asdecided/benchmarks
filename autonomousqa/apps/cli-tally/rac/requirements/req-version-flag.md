---
schema_version: 1
id: TALLY-0000000000R1
type: requirement
---

# The Version Flag Identifies the Tool

## Status

Accepted

## Problem

Scripts and users pin behaviour to a tool version; the tool must state its
identity on request.

## Requirements

- [REQ-001] The tool SHALL print exactly `tally 1.0.0` on stdout when invoked with `--version`.
- [REQ-002] The version invocation SHALL exit with code 0.

## Acceptance Criteria

- Running `tally.py --version` prints `tally 1.0.0` and exits 0.
