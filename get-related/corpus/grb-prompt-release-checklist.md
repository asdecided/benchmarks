---
schema_version: 1
id: GRB-GTR8ZA397CM1
type: prompt
tags: [docs]
---
# Release Notes Checklist

## Status

Active

## Objective

Check a drafted release note against the shipped change list before it is published.

## Input

The drafted note and the list of shipped changes.

## Instructions

Flag any shipped change the note omits and any note claim with no shipped change behind it. Do not rewrite the note; only report findings.

## Output

Two lists: omissions and unsupported claims, each with one line of evidence.

## Constraints

Report only mismatches; an empty finding list is a valid result.
