---
schema_version: 1
id: SAB-DXPP6KEYYVC7
type: design
tags: [alerting]
---
# Alert Rule Editor

## Status

Accepted

## Context

Attaching an alert to a tile today means writing a rule expression by hand, which only power users attempt.

## User Need

A board viewer needs to create a sensible threshold alert in under a minute without learning an expression language.

## Design

The editor opens from any numeric tile with the metric pre-filled. It offers threshold, change-over-window, and absence conditions as guided forms, previews the rule against the last week of data, and shows which destinations will be notified.

## Constraints

Every rule the guided forms produce must round-trip to the expression language, so power users can open and refine it.

## Rationale

Guided forms over a real expression keep the easy path easy without capping the ceiling.

## Related Requirements

- SAB-XRTP8KP80P17
