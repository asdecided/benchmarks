---
schema_version: 1
id: DG-KWRRC0E9R6Y4
type: decision
tags: [statistics, significance, mcnemar, publication, methodology]
---
# Report Paired Significance as Exact McNemar with Paired Effect Sizes

## Context

The publication study (rac-core `rac-grounding-baseline-study`, REQ-005)
requires publication-grade inference: a pre-registered hypothesis, paired
significance testing per co-primary outcome, and effect sizes with confidence
intervals. The variance-reporting decision (DG-KVPXSF1B0PW8) gave the
crossover mean ± t-CI curves and a paired rac−naive_rag difference, but no
hypothesis test: there is no p-value a reviewer can check the falsifier
against, and the aggregated datasets kept only per-scenario *fractions*,
destroying the per-cell booleans a paired test needs. Every arm answers the
same scenario under the same seed and distractor draw (common random
numbers), so the natural test is a paired one on the discordant cells.

## Decision

- Add `scoring/stats.py`: **exact McNemar** (two-sided binomial on the
  discordant counts — no chi-square approximation, no continuity fudge),
  **Wilson score intervals** on marginal rates, a **paired risk difference**
  with a Wald CI, and a **conditional odds ratio** with a Wilson-transformed
  CI. Zero-cell tables are flagged `degenerate`, never Haldane-smoothed.
- Retain the raw per-cell booleans in crossover datasets (a `cells` list of
  `{seed, N, arm, scenario_id, adherent}`) and attach a per-N `stats` block;
  run reports gain the same block paired by scenario. Legacy datasets without
  cells merge with `stats: null` rather than a reconstruction from fractions.
- Statistics are **stdlib-only** (`math.comb`), deterministic, and
  order-independent: the same records always produce byte-identical output.
- The paired unit is **scenario** (base-N reports) or **scenario × seed**
  (crossover, common random numbers). The confirmatory pair is
  **rac vs naive_rag**; other pairs are reported context. The full analysis
  plan is pre-registered as an additive frozen amendment in
  `spec/analysis-plan-amendment-1.md`.
- Everything here is **analysis, never a gate**: no CI job consumes a
  p-value, and the scored path is untouched (rac-core ADR-066 / ADR-097).
  The headline remains the single legible adherence rate.

## Consequences

### Positive

- The falsifier verdict carries a checkable exact p-value and effect sizes,
  not only a CI band; the paper's statistics regenerate from the dataset.
- Per-cell retention makes any future paired analysis possible without
  re-running paid sweeps.
- No new dependency; offline determinism preserved.

### Negative / Risks

- Datasets grow by one record per (seed, N, arm, scenario) cell — accepted;
  the records are small and the statistical value is the point.
- The exact test is conservative at tiny discordant counts; that honesty is
  preferred over approximations.

## Status

Accepted

## Category

Technical

## Alternatives Considered

- **Chi-square McNemar with continuity correction.** Rejected: an
  approximation with tuning knobs where the exact binomial is trivial at this
  scale and has none.
- **Bootstrap significance.** Rejected: resampling adds nondeterminism (or a
  seeded RNG to argue about) for no gain over an exact test on paired
  booleans.
- **Only the existing seed-level CI on the paired difference.** Rejected as
  incomplete: REQ-005 asks for significance tests and effect sizes per
  outcome; the seed-CI stays as supporting variance evidence.
- **SciPy.** Rejected: a heavy dependency for `comb` arithmetic the stdlib
  provides (consistent with DG-KVPXSF1B0PW8).

## Related Decisions

- DG-KVPXSF1B0PW8
- DG-KWRRC1NTBW25
