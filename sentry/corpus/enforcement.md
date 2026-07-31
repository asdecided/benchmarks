---
schema_version: 1
id: SEN-C3D4E5F6G7H8
type: decision
tags: [fixture, enforcement]
---
# Decision: Enforce Repository Boundaries

## Status

Accepted

## Context

The fixture repository needs representative source boundaries.

## Decision

Hard deletion and direct database dependencies are forbidden, while the audit
entry point must remain present.

## Consequences

Sentry can exercise every version-one rule family.

## Code Constraints

```yaml
version: 1
eligibility: eligible
rules:
  - id: no-hard-delete
    kind: forbid_pattern
    path_glob: "src/**/*.sql"
    pattern: "(?i)DELETE\\s+FROM\\s+users"
    message: "User records must not be hard-deleted."
  - id: require-audit-entrypoint
    kind: require_pattern
    path_glob: "src/audit.rs"
    pattern: "pub fn audit"
    message: "The public audit entry point must remain present."
  - id: no-python-db-import
    kind: forbid_import
    path_glob: "src/**/*.py"
    pattern: "^(sqlalchemy|psycopg)(\\.|$)"
    message: "Python services must not import database clients directly."
  - id: no-rust-db-import
    kind: forbid_import
    path_glob: "src/**/*.rs"
    pattern: "^(diesel|sqlx)(::|$)"
    message: "Rust services must not import database clients directly."
  - id: no-js-db-import
    kind: forbid_import
    path_glob: "src/**/*.{js,jsx,ts,tsx,mjs,cjs}"
    pattern: "^(pg|typeorm)(/|$)"
    message: "JavaScript services must not import database clients directly."
  - id: reject-unsupported-import-language
    kind: forbid_import
    path_glob: "src/**/*.go"
    pattern: "^database/sql$"
    message: "Selected languages without a deterministic adapter must fail closed."
```

## Category

Architecture
