---
schema_version: 1
id: SAB-WDFKCA6HA0Z5
type: prompt
tags: [operations]
---
# Draft Incident Report

## Status

Active

## Objective

Turn an incident channel transcript into a structured post-incident report.

## Input

The incident channel transcript, the severity classification, and the resolution time.

## Instructions

Extract the timeline, impact, root cause, and follow-ups. Attribute actions to roles rather than names. Keep speculation out of the root cause section.

## Output

A report with Timeline, Impact, Root Cause, and Follow-ups sections.

## Constraints

Only statements supported by the transcript; mark open questions explicitly.
