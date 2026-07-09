# HTTP Client Timeout (v2)

Status: Active

## Decision

The team must not call the payment gateway using the blocking http client function; the async client module is now required and the blocking function is not permitted.
This decision supersedes DG-ADR-HTTP-001.

