---
schema_version: 1
id: SAB-DPP0QKXKFS4H
type: requirement
tags: [compliance]
---
# Query Audit Logging

## Status

Accepted

## Problem

Regulated customers must prove who looked at which figures. Meridian keeps no record of reads, which blocks those deals.

## Requirements

- [REQ-001] Every executed query MUST append an audit record naming the principal, the board, and the time.
- [REQ-002] Audit records MUST be immutable and retained for seven years.
- [REQ-003] Workspace admins MUST be able to filter the audit trail by principal and date range.

## Success Metrics

- The audit trail satisfies the reference customer's compliance review.
