---
schema_version: 1
id: SAB-11PXKZKPAJG2
type: decision
tags: [reporting]
---
# Parquet Report Export

## Status

Accepted

## Context

Analysts now pull whole datasets into warehouse and notebook tools, which read columnar files natively and preserve types.

## Decision

Report export produces Parquet files: a columnar format with explicit column types, generated asynchronously and delivered by signed link.

## Consequences

Exports carry precise types at any size. Consumers on plain spreadsheets need a converter step.

## Category

Technical

## Supersedes

- SAB-Z4R5ADGAVT1J
