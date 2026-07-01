---
schema_version: 1
id: SAB-57CCMCV2X424
type: prompt
tags: [docs, ingestion]
---
# Draft Connector Documentation

## Status

Active

## Objective

Draft the catalog entry for a new data source connector from its registry metadata.

## Input

The connector's registry metadata: source system, authentication methods, datasets, and sync modes.

## Instructions

Describe what the connector syncs, each authentication method, and the sync latency class in plain language. Note dataset-level limitations verbatim from metadata.

## Output

A catalog entry with Overview, Authentication, Datasets, and Sync Behaviour sections.

## Constraints

Every statement must trace to a metadata field; no capability invention.
