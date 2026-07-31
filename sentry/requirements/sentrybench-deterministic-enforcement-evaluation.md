---
schema_version: 1
id: SEN-B2C3D4E5F6G7
type: requirement
tags: [benchmark, sentry, conformance]
---
# Requirement: SentryBench Deterministic Enforcement Evaluation

## Status

Accepted

## Problem

AsDecided needs reproducible evidence that Sentry catches machine-checkable
decision violations without blocking compliant changes or overstating corpus
coverage.

## Requirements

- [REQ-001] The benchmark MUST invoke AsDecided only through an external `decided` CLI.
- [REQ-002] Scored correctness MUST be deterministic, offline, and free of model judgement.
- [REQ-003] Every supported rule kind MUST have blocking and allowing cases.
- [REQ-004] Diff mode MUST prove new-line isolation for introduced, pre-existing, removed, adjacent, and unrelated changes.
- [REQ-005] Findings MUST be checked for code, decision, rule, path, and available line attribution.
- [REQ-006] JSON output MUST be byte-identical across repeated unchanged runs.
- [REQ-007] SARIF MUST identify the same violation and source location as JSON.
- [REQ-008] `decided sentry` and `decided gate --code` MUST agree on their shared finding projection and coverage; dedicated Sentry JSON MUST retain decision and rule attribution.
- [REQ-009] Invalid constraints and unsupported selected import languages MUST fail closed.
- [REQ-010] Performance measurements MUST remain outside the scored metrics block.
- [REQ-011] The gate MUST require perfect conformance, violation recall, clean-pass rate, attribution, report accuracy, parity, and determinism.

## Success Metrics

- All committed correctness cases pass.
- Violation recall and clean-patch pass rate are both 1.0.
- Attribution, SARIF, gate parity, and determinism are all 1.0.
- A deliberately contradicted case fails the benchmark gate.

## Risks

- Synthetic fixtures may be easier than real repositories; mutation and external-repository tranches must follow.
- Regex rules can be correct for a fixture but too broad for production; every rule therefore needs a near-neighbour allow case.
- Runtime measurements vary by host; they are diagnostic until a controlled runner profile is established.
- The composed gate does not yet expose Sentry decision and rule fields; parity is limited to code, path, line, outcome, and coverage until that payload grows additively.

## Assumptions

- Git is available locally for diff fixtures.
- The tested AsDecided release supports `decided sentry` and `decided gate --code`.

## Related Decisions

- SEN-ADR-0001

## Verified By

- sentry/run.py
- tests/test_sentry_benchmark.py
