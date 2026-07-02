---
schema_version: 1
id: SAB-7XZ3T9DXXSQY
type: design
tags: [multitenancy]
---
# Tenant Switcher

## Status

Accepted

## Context

Agency users belong to many customer workspaces and today sign out and back in to move between them.

## User Need

A user in several tenants needs to switch context in one gesture and always know which tenant they are acting in.

## Design

A persistent workspace badge in the top bar opens a switcher listing the user's tenants with their roles. Switching swaps the whole context atomically and repaints the badge colour.

## Constraints

The active tenant must be unambiguous on every screen; the badge is never hidden, even in presentation mode.

## Rationale

An always-visible badge prevents the cross-tenant mistakes that sign-out juggling was silently causing.

## Related Decisions

- SAB-TQDNAG5W1PZM
