---
schema_version: 1
id: SAB-2TXN09NNT01N
type: prompt
tags: [support]
---
# Triage Support Tickets

## Status

Active

## Objective

Classify incoming support tickets by product area and urgency for routing.

## Input

A batch of raw ticket subjects and bodies.

## Instructions

Assign each ticket one product area from the fixed list and an urgency of low, normal, or breach. Quote the phrase that justified any breach rating.

## Output

One line per ticket: area, urgency, justification quote when breach.

## Constraints

Never invent an area outside the fixed list; prefer normal when uncertain.
