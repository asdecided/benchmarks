---
schema_version: 1
id: DG-KVPW3XG9TDZY
type: decision
tags: [publication, naming, paper, positioning]
---
# Name the Benchmark SWE-DecisionBench and Publish a Methodology Preprint

## Context

The benchmark needs a public identity for an arXiv preprint. Its nearest
neighbour is SWE-ContextBench (arXiv:2602.08316), which shows accurately retrieved
context helps coding agents while unfiltered context hurts — the same gradient our
`context_dump → naive_rag → rac` arms measure. The `SWE-*` prefix (SWE-bench,
SWE-ContextBench) is a recognised family in the coding-agent benchmark space, so a
name in that family maximises discoverability and positions us directly beside the
closest related work.

Caveat: `SWE-` connotes repo-patching / issue-resolution (the SWE-bench lineage),
whereas our task is *decision adherence* over standards-style corpora (PEP/RFC/W3C
supersession), not "make the tests pass." The name slightly leans into the
coding-agent framing the README already commits to.

## Decision

- Brand the benchmark **SWE-DecisionBench** in the paper and public materials.
- Keep the repository and Python package named `decisiongrounding` for now (a
  rename is higher-churn and can follow if warranted); the paper carries the
  brand via a single `\benchname` LaTeX macro so it stays swappable.
- Target a **benchmark + methodology preprint** (the genre SWE-ContextBench
  occupies), not a broad multi-model empirical paper — the controlled,
  deterministic single-variable design and the real, reproducible corpora are the
  contribution. A stronger empirical claim (multiple models/seeds) is future work.

## Consequences

### Positive
- Discoverability and clear positioning next to SWE-ContextBench.
- The `\benchname` macro makes the name a one-line change if we reconsider.

### Negative / Risks
- `SWE-` may over-signal the patch-resolution genre; mitigated by an explicit
  scope statement in the paper's method and limitations.
- A single-model, ~19-scenario pilot is thin for a headline empirical claim;
  scoped as methodology + pilot, with multi-model/seed work flagged as future.

## Status

Accepted

## Category

Product

## Alternatives Considered

- **DecisionBench (no `SWE-`).** More accurate to scope and future-proof if we
  broaden beyond code, but forgoes the `SWE-*` family discoverability.
- **Keep `decisiongrounding` only.** Lowest churn, weakest positioning.
- **SWE-DecisionGrounding.** In-family and explicit, but long for a title.

## Related Roadmaps

- DG-KVPW3E3J2A79
