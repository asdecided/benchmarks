---
schema_version: 1
id: GRB-FBXMXWKHGFXE
type: roadmap
tags: [deploys]
---
# Continuous Delivery

## Status

Planned

## Context

Harbor releases weekly with a human at every gate. The programme moves to releasing every merge with humans only at the review.

## Outcomes

- Every merged change reaches production the same day unattended.
- Rollback is routine enough that nobody announces it.

## Initiatives

- Automate the colour shift end to end.
- Make the smoke suite the only release gate.
- Retire the weekly release calendar.

## Success Measures

- Merge-to-production median under one hour.

## Related Decisions

- GRB-4D11EAG0GAB9
