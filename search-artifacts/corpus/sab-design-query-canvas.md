---
schema_version: 1
id: SAB-6GWSQRB4HCEB
type: design
tags: [queries]
---
# Query Builder Canvas

## Status

Accepted

## Context

New users bounce off the query editor because it opens with an empty text box that assumes the query language.

## User Need

An analyst needs to compose a measurement query by direct manipulation and only drop to text when they want to.

## Design

A canvas where the analyst picks a measurement, then stacks filter, group, and aggregate blocks. The canvas renders the resulting chart continuously and shows the generated query text in a collapsible pane.

## Constraints

Every canvas state must serialize to the query language exactly; the text pane is the same query, never an approximation.

## Rationale

Blocks-over-text mirrors how analysts describe questions aloud, while the visible query text keeps the ceiling and teaches the language.
