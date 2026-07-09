# Cache Write in Request Handlers

Status: Active

## Decision

The team must not write computed totals into the shared cache module standard library function from a request handler; the request handler cache module write is not permitted because it corrupts the batch module totals.
