# Typing Module Public API Changes

Status: Active

## Decision

The team must not rewrite the typing module public annotation API or change its exported type syntax without explicit architecture authorization. Any change to the standard typing interface requires sign-off, because downstream packages import these types directly.
