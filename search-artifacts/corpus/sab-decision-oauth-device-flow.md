---
schema_version: 1
id: SAB-140F1RA59TET
type: decision
tags: [auth]
---
# OAuth Device Flow Sign-In

## Status

Accepted

## Context

Wall-mounted displays and CLI users cannot type credentials into an embedded browser. Meridian needs a sign-in path for input-constrained surfaces.

## Decision

Input-constrained clients sign in with the OAuth device flow: the client shows a short code, the user approves it from any signed-in browser, and the client polls the token endpoint for the grant.

## Consequences

Displays and terminals sign in without embedded browsers. The approval page becomes a phishing-sensitive surface and carries the standard warnings.

## Category

Technical
