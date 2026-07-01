---
schema_version: 1
id: SAB-HWQ2HK2T61MX
type: requirement
tags: [sharing, access]
---
# Dashboard Sharing Permissions

## Status

Accepted

## Problem

Boards are either private or fully public inside the workspace today, so sensitive revenue boards get duplicated into screenshots instead of shared.

## Requirements

- [REQ-001] Board owners MUST be able to share a board with named people or groups as viewer or editor.
- [REQ-002] A shared board MUST enforce the viewer role server-side on every query, not only in the interface.
- [REQ-003] Owners MUST be able to revoke a share and see when it was last used.

## Success Metrics

- Screenshot-sharing of revenue boards drops to zero in the quarterly audit.

## Related Decisions

- SAB-TQDNAG5W1PZM
