---
schema_version: 1
id: DG-ADR-0004
type: decision
tags: [corpus, crossover, methodology]
---

# ADR-0004: The Adherence-vs-N Curve Scales With Real PEP Distractors

## Status

Accepted

## Category

Technical

## Context

The headline artifact is the decision-adherence-vs-corpus-size curve over
N ∈ {10, 50, 150, 300}. Until now the corpus was grown with synthetic,
clearly-labelled `note` filler (see `scoring/crossover.py`,
`make_filler_notes`). That filler is honest about being illustrative — it is
explicitly *not* a real corpus — but it has two weaknesses as evidence:

1. It is typed `note`, never `decision`. A typing-aware arm (`rac`,
   `context_dump`) trivially ignores it, and a typing-blind arm (`naive_rag`)
   only has to out-rank chatter. Real deployments do not pad a decision corpus
   with obvious non-decisions; they accumulate *many real decisions*, only a few
   of which bind any given task.
2. CONTRIBUTING.md rule 2 requires real/public-derived corpus material for
   published results. Synthetic filler cannot back a published curve.

ADR-0002 established the PEP supersession pilot as the first real corpus and
ADR-0003 wired the `rac` arm to it. This ADR extends that vein to the *scaling
distractors* the curve needs.

## Decision

Grow the curve with **real, public PEP decision artifacts as distractors**,
drawn from a pinned pool, replacing synthetic filler for real runs.

- `ingest.peps pool build` scans a pinned PEP number range (`POOL_RANGE`,
  default 1–700) at the pinned commit, ingesting every PEP that exists as a
  RAC-native `decision` artifact — identical envelope derivation to the pilot
  (ADR-0002/0003), so the pool carries real `supersedes` edges too. Gaps in the
  numbering are skipped; the exact included set + per-PEP sha256 are recorded in
  `provenance.json`, which `pool verify` re-checks byte-for-byte.
- The pool's `provenance.json` is committed (the auditable pin); the bulky
  verbatim corpus is rebuilt on demand and gitignored. Determinism and audit do
  not require shipping ~12 MB of upstream `.rst`.
- `scoring.crossover.make_real_distractors` deterministically samples the pool
  (seeded by `seed`, scenario id, and N), excluding the scenario's own corpus
  ids so a distractor never collides with the binding decision or the one it
  supersedes. `build_dataset(..., pool=...)` selects this path; the runner
  exposes it as `demo --distractors real --pool <dir>`.

The synthetic-filler path is retained for the zero-credential offline demo and
is still labelled illustrative; `crossover_dataset.json` records which was used
(`distractors`, `pool_size`).

## Consequences

### Positive

- The curve can be backed by real, public, reproducible decisions — a far
  harder and fairer distractor set, since a typing-blind retriever can no longer
  dismiss distractors as non-decisions.
- The pool is a pin, not a content dump: `provenance.json` + `pool verify` make
  it auditable and reproducible without committing the corpus bytes.
- Real `supersedes` edges inside the pool exercise the `rac` arm's traversal at
  realistic scale.

### Negative

- A real run must build the pool first (one network pass) and, for `naive_rag`,
  use a real embedder — more setup than the offline demo.

### Risks

- **A single discriminating scenario is a thin curve.** With only the PEP
  386→440 pilot, the curve averages one scenario, and if its governing decision
  is strongly task-similar even naive RAG retrieves it — so the offline
  (BoW-embedder) curve shows no crossover. Mitigation: the pool already exposes
  ~28 real `supersedes` edges; additional discriminating scenarios derived from
  them (each with a hand-authored, blind gold label per rule 1) are the next
  increment, and the real crossover is only claimed once the Voyage embedder and
  ≥ a few real scenarios are in play.

## Alternatives Considered

#### Keep synthetic filler only
Simplest, but cannot back a published curve (rule 2) and under-tests
typing-blind retrieval. Rejected as evidence; retained only for the offline demo.

#### Commit the full pool corpus
Reproducible, but ships ~12 MB of upstream bytes the pin already determines.
Rejected: `provenance.json` + `verify` give the same guarantee leaner.

## Related Decisions

- DG-ADR-0002 (extends the real-corpus pilot to scaling distractors)
- DG-ADR-0003 (reuses the RAC-native PEP envelope for pool artifacts)

## Success Measures

A real-embedder run at N ∈ {10,50,150,300} over the real pool produces a
per-arm adherence curve whose movement is explained by governing-decision
recall, on real public decisions, fully reproducible from the pin.

## Review Date

When the second real discriminating scenario lands, or before the first
published curve — whichever comes first.
