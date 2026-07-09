# Async Import in Request Modules

Status: Active

## Decision

The team must not use the async import loader function inside a request handler module; the request module async import is not permitted because it blocks the standard library package load.
