---
schema_version: 1
id: DG-KWRRC1NTBW25
type: decision
tags: [benchmark, outcomes, resolution, publication, gitchameleon]
---
# SWE-DecisionBench Reports Two Co-Primary Outcomes

## Context

SWE-DecisionBench (DG-KVPW3XG9TDZY) borrows the SWE- family name, and the
family (SWE-bench, SWE-ContextBench) implies real-repository, executable
verification — not only structural inspection of a proposed change. The
rac-core publication requirement (`rac-grounding-baseline-study`, REQ-002/003)
makes that expectation explicit: the published study must report executable,
decision-conditioned task success alongside structural decision-adherence,
both deterministic. The executable seam already exists as the sibling
`gitchameleon/` member (GCB-329CD3DAMG8Y): version-conditioned problems whose
correct answer depends on a recorded version-pin decision, scored by the
upstream harness's executable tests.

## Decision

- The published SWE-DecisionBench study reports **two co-primary outcomes**:
  1. **Decision-adherence** — structural, scored by this member's
     deterministic scorer; the novel construct.
  2. **Decision-conditioned resolution** — executable pass rate on the
     GitChameleon evidence run, per arm, under the no-version-in-prompt
     protocol; the upstream test harness is the scorer and we add none.
- Co-primary means each claim stands alone: neither outcome is demoted to
  "secondary", and the conjunction is claimed only if both hold.
- The **honesty rule extends to both outcomes**: a mixed result (adherence
  wins, resolution does not — or the reverse) is a publishable finding,
  reported plainly, never suppressed.
- The resolution arm produces per-(example, arm) paired records that feed the
  same paired analysis as adherence (DG-KWRRC0E9R6Y4), with `passed` as the
  outcome.
- Boundaries hold: the GitChameleon run remains an **evidence run, never a
  merge gate**; its results are not comparable to the upstream leaderboard;
  the `rac` CLI is driven externally; nothing embedding- or judge-shaped
  enters any scored path (rac-core ADR-066 / ADR-092 / ADR-097).

## Consequences

### Positive

- The SWE- name is earned rather than borrowed: executable verification is
  co-primary, not an appendix.
- One statistical framework covers both outcomes, so the paper's analysis
  section is a single method applied twice.

### Negative / Risks

- The funded run now spans two benchmarks (crossover + GitChameleon), raising
  cost and infrastructure (per-version dependency installs for upstream
  scoring). The funded-run handoff budgets both.
- A thin executable result would weaken the family claim; the pre-registered
  falsifier for the resolution outcome keeps that failure honest rather than
  hidden.

## Status

Accepted

## Category

Product

## Alternatives Considered

- **Adherence-only publication.** Rejected: rac-core REQ-002 makes executable
  resolution mandatory for the SWE- name; adherence alone invites the
  "borrowed badge" critique recorded in the requirement's risks.
- **Building an executable scorer inside this member.** Rejected: the
  upstream harness already scores deterministically; adding our own scorer
  would create a parallel, less credible verdict (GCB-ADR-0001 scope).
- **Folding gitchameleon into decisiongrounding.** Rejected: one repo per
  concern, subdir per member (rac-core ADR-092); the members share statistics
  code, not identity.

## Related Decisions

- DG-KVPW3XG9TDZY
- DG-KWRRC0E9R6Y4
- DG-KVPXSF1B0PW8
