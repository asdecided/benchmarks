---
schema_version: 1
id: GRB-5W12JRBWBRP5
type: design
tags: [deploys, ci]
---
# Release Pipeline

## Status

Accepted

## Context

Release steps lived in a runbook executed by hand, and the runbook drifted from reality every quarter.

## User Need

An engineer shipping a change needs one pipeline that takes it from merge to shifted traffic with no manual step.

## Design

The pipeline builds once, deploys the artifact to the idle colour, runs the smoke suite there, shifts traffic on green, and parks the old colour warm for the rollback window.

## Constraints

Every step must be idempotent so a resumed pipeline never repeats a side effect.

## Rationale

Encoding the runbook as a pipeline is the only way it stays true.

## Related Decisions

- GRB-4D11EAG0GAB9

## Related Requirements

- GRB-65C1EA6PXMR7
