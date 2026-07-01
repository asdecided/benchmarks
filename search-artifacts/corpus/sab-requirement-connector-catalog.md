---
schema_version: 1
id: SAB-A75HC5ZWR0E1
type: requirement
tags: [ingestion]
---
# Data Source Connector Catalog

## Status

Accepted

## Problem

Every new customer asks which systems Meridian can ingest from, and the answer lives in a sales spreadsheet nobody maintains.

## Requirements

- [REQ-001] The product MUST ship a browsable connector catalog listing every supported source system with its sync modes.
- [REQ-002] Each connector entry MUST state its authentication methods and sync latency class.
- [REQ-003] The catalog MUST be generated from the connector registry so it can never drift from shipped connectors.

## Success Metrics

- Presales connector questions answered by a catalog link in over 80% of cases.
