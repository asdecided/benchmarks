---
schema_version: 1
id: GSB-GZBV63EBPN3Z
type: design
tags: [capture]
---
# Capture Bar

## Status

Accepted

## Context

The capture shortcut needs a surface that appears instantly over whatever the person is doing.

## User Need

Someone mid-task needs to bank a thought and return to their task in one breath.

## Design

A floating one-line bar summoned by the global shortcut. It accepts text immediately, grows to a paragraph if typing continues, and dismisses on enter, filing to the inbox.

## Constraints

The bar must render before any store read completes; it writes asynchronously after dismissal.

## Rationale

A disposable surface beats opening the app: the cost of capture must be lower than the cost of the interruption.

## Related Requirements

- GSB-ME7EY2ZE6KSQ
