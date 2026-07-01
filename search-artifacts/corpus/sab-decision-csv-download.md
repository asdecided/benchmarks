---
schema_version: 1
id: SAB-Z4R5ADGAVT1J
type: decision
tags: [reporting]
---
# CSV Download

## Status

Superseded

## Context

Analysts wanted board figures in their spreadsheet tools. The quickest path was a plain comma-separated download of the visible table.

## Decision

Every table tile offers a comma-separated download of exactly the rows on screen, generated synchronously in the request.

## Consequences

Trivially compatible with spreadsheets, but large tables time out and numeric types round-trip badly. Replaced by a typed alternative.

## Category

Technical
