---
schema_version: 1
id: SAB-9FB3XRTNKWM7
type: design
tags: [ingestion]
---
# Connector Onboarding Flow

## Status

Accepted

## Context

Setting up a source today is a support-guided tour of credentials, scopes, and sync options across three settings pages.

## User Need

A workspace admin needs to connect a new source system end to end without a support call.

## Design

A single guided flow: pick the source from the connector catalog, authenticate with the method the entry declares, choose datasets and sync cadence, and watch a first-sync progress screen that surfaces errors inline.

## Constraints

The flow is generated from connector metadata; adding a connector must not require flow changes.

## Rationale

One metadata-driven flow scales to every connector without bespoke screens.

## Related Requirements

- SAB-A75HC5ZWR0E1
