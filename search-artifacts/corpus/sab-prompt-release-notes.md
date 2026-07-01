---
schema_version: 1
id: SAB-A1B6ZNP94CCX
type: prompt
tags: [docs, release]
---
# Generate Release Notes

## Status

Active

## Objective

Draft human-readable release notes for a Meridian release from its merged change list.

## Input

The merged change titles and descriptions for the release, plus the previous and new version numbers.

## Instructions

Group changes into Features, Fixes, and Internal. Write one plain-language bullet per change describing the user-visible effect. Lead with the most visible features.

## Output

Markdown release notes: a version heading, then the three grouped sections.

## Constraints

Do not invent changes that are not in the input. One sentence per bullet.
