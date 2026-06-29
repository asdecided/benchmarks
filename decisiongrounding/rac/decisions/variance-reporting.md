---
schema_version: 1
id: DG-KVPXSF1B0PW8
type: decision
tags: [statistics, variance, crossover, methodology]
---
# Report Crossover Results as Mean ± CI with a Paired rac−naive_rag Difference

## Context

The adherence-vs-N crossover is a single-seed point estimate. The curve depends on
*which* real distractors happen to bury the governing decision — a seeded draw —
and the answering model is stochastic. A single seed can therefore mislead, and
the pre-registered falsifier ("grounded ≈ naive_rag on superseded + prohibition at
N ≥ 50") needs error bars, not one number. Arms are already paired on the seed
(same distractors per (N, seed) across arms, in `scoring/crossover.py`), so the
*difference* between arms at a fixed seed isolates grounding on an identical
corpus — a low-variance, common-random-numbers comparison.

## Decision

- Report each (arm, N) curve point as **mean ± a t-based 95% confidence interval**
  across seeds. The mean stays in the existing fields (`adherence_rate`,
  `governing_recall`, token means) for backward compatibility; CI, std, and the
  per-seed values are added alongside.
- Treat the **paired `rac − naive_rag` difference** (per N, differenced within each
  seed, then averaged) **with its own CI** as the headline falsifier statistic:
  the thesis is supported at an N only if that difference's CI lies above zero.
- Compute statistics **without SciPy** — a small hardcoded Student-t table
  (df 1–29, → 1.96 for df ≥ 30) over `statistics.mean`/`stdev`. This keeps the
  core dependency-free (consistent with the project's offline-first stance).
- Default to **5 seeds**, with append-friendly aggregation (add seeds later without
  re-running prior ones). Escalate to ~10 only at decision-critical N if the paired
  CI straddles zero.

## Consequences

### Positive
- The crossover and the falsifier verdict carry uncertainty, not a single point.
- Pairing makes the comparison resolvable with few seeds (cheap).
- No new runtime dependency; offline determinism preserved.

### Negative / Risks
- A real `--seeds k` run multiplies spend ×k (and ×models).
- Offline runs show little/no spread (deterministic stub + embedder); meaningful
  variance comes from the real model and distractor-draw changes at larger N — so
  tests assert aggregation correctness, not non-zero spread.
- A hardcoded t-table is approximate at the third decimal; acceptable for 95% CIs
  at small n.

## Status

Accepted

## Category

Technical

## Alternatives Considered

- **Normal-approx (z = 1.96) CIs.** Rejected for small n: understates the interval;
  t is the honest choice for ~5 seeds.
- **Bootstrap CIs.** More machinery and non-determinism for no real gain at this n.
- **Per-arm CIs only (no paired difference).** Rejected: the falsifier is about the
  *gap*; the unpaired per-arm CIs are wider and waste the common-random-numbers
  pairing the harness already provides.
- **Add SciPy for `scipy.stats.t`.** Rejected: a heavy dependency for one critical
  value; a small table suffices.

## Related Decisions

- DG-KVMRV4YRMJB6

## Related Designs

- DG-KVPXS090VR5N
