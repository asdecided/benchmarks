---
schema_version: 1
id: TALLY-0000000000R2
type: requirement
---

# Sum Prints the Total of Its Arguments

## Status

Accepted

## Problem

The tool's core job is turning a list of numbers into their total, printed
plainly so shells can capture it.

## Requirements

- [REQ-001] The tool SHALL print the integer total of the numbers given to the `sum` command on stdout.
- [REQ-002] A successful `sum` invocation SHALL exit with code 0.

## Acceptance Criteria

- Running `tally.py sum 3 4 5` prints `12` and exits 0.
