---
schema_version: 1
id: GSB-H0HV5F5A434E
type: prompt
tags: [capture]
---
# Structure Meeting Notes

## Status

Active

## Objective

Turn a raw capture from a meeting into a structured note.

## Input

The raw captured text and the meeting title from the calendar.

## Instructions

Split the capture into decisions made, actions with owners, and open questions. Preserve the author's wording inside each bucket.

## Output

A note with Decisions, Actions, and Open Questions sections.

## Constraints

Never add content that is not in the capture; unassigned actions stay unassigned.
