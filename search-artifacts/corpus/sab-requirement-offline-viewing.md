---
schema_version: 1
id: SAB-FK8CDGGX4SAR
type: requirement
tags: [mobile, offline]
---
# Offline Dashboard Viewing

## Status

Accepted

## Problem

Field engineers open boards from sites with no coverage. Today the app shows an error where the figures were, which makes the mobile app useless exactly where it is most needed.

## Requirements

- [REQ-001] The mobile app MUST retain the last rendered state of every board the user has opened and show it when no network is available.
- [REQ-002] A board rendered from retained state MUST carry a visible banner with the age of the figures.
- [REQ-003] The app MUST refresh retained boards automatically when coverage returns.

## Success Metrics

- A board opened in airplane mode renders its retained state in under one second.
- Zero support tickets about blank boards on site visits.
