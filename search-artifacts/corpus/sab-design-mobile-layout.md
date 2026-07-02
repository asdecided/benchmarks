---
schema_version: 1
id: SAB-0VH83YT5R8Q7
type: design
tags: [dashboard, mobile]
---
# Mobile Dashboard Layout

## Status

Accepted

## Context

Phone screens cannot honour the desktop arrangement, and pinch-zooming a desktop board is unusable in the field.

## User Need

A viewer on a phone needs every tile legible at arm's length without horizontal scrolling.

## Design

On narrow screens the board reflows into a single column ordered by the author's declared priority, one full-width tile per row. Charts trade detail for a large headline figure.

## Constraints

Reflow is derived from the desktop arrangement automatically; authors override only the priority order, never a second arrangement.

## Rationale

One source arrangement with a derived reflow keeps authoring cost flat while making phones first-class viewers.

## Related Requirements

- SAB-FK8CDGGX4SAR
