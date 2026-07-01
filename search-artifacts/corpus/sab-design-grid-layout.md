---
schema_version: 1
id: SAB-83EGQYPTSMHV
type: design
tags: [dashboard, desktop]
---
# Dashboard Grid Layout

## Status

Accepted

## Context

Desktop boards hold a dozen or more tiles, and authors arrange them to tell a story. The arrangement surface determines how deliberate that story can be.

## User Need

A board author on a wide screen needs to place, size, and align tiles precisely and predictably.

## Design

The desktop board is a twelve-column grid. Tiles snap to grid cells, drag to reposition, and resize by their corner handles; the grid draws alignment guides while a tile moves.

## Constraints

Tile positions are stored in grid units, never pixels, so boards render identically across screen densities.

## Rationale

A fixed-column grid with snapping gives authors precision without a free-form canvas's alignment drudgery.
