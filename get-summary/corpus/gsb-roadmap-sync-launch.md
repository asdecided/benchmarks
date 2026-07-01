---
schema_version: 1
id: GSB-RYSBB3X0T9C0
type: roadmap
tags: [sync]
---
# Sync Launch

## Status

Planned

## Context

Quill is single-device today; the sync launch makes the corpus follow the person across devices without giving up local-first guarantees.

## Outcomes

- A second device converges to the same corpus within a minute of coming online.
- No edit is ever lost to a conflict.

## Initiatives

- Ship blob sync over the encrypted channel.
- Ship the merge policy for concurrent edits.
- Ship key enrolment for new devices.

## Success Measures

- Multi-device users retain at double the single-device rate.

## Related Decisions

- GSB-N4769N88GCX3
- GSB-8PW67GGPHT7R
