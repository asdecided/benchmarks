---
schema_version: 1
id: SAB-S88S6QYGH14V
type: prompt
tags: [docs]
---
# Summarize Dashboard Changes

## Status

Active

## Objective

Write the weekly change summary for a board so reviewers know what moved and why.

## Input

The board's figure deltas week over week and its annotation stream.

## Instructions

Lead with the largest movements. Tie each movement to an annotation when one exists; otherwise say it is unexplained. Keep to five bullets.

## Output

Five bullets, largest movement first, each naming the tile and the delta.

## Constraints

Never smooth over an unexplained movement; unexplained is a finding.
