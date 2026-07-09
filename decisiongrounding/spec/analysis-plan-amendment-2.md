# Analysis Plan — Amendment 2 (correction: error cells excluded from rates)

*Dated 2026-07-09. An **additive** correction to the reporting/analysis layer.
It changes no gold labels, no scoring rubric, and no confirmatory test defined
in Amendment 1 (FROZEN); it corrects a defect in how the crossover builder
computed `adherence_rate` and the paired statistical record, bringing that
path into line with the base-N table, which was already correct. Per the
taxonomy's rule, this is a new spec version rather than an edit to
Amendment 1.*

## The defect

Amendment 1 states that the paired adherence analysis is over **completed
cells** — cells that produced a scored answer. The base-N table already
honoured this: a cell that errored never produced a `Score`, so it was
absent from `adherence_rate` and reported separately as coverage
(`n_errors`, `n_context_exceeded`).

The crossover builders (`scoring/crossover.py`) honoured it for
context-window-exceeded (CWE) cells only. A cell that failed with **any other
error** — a structured-output schema miss, a gateway HTTP rejection, a
transport/network failure — was forced to `adherent=False` and then counted
as a genuine non-adherent observation: in the `adherence_rate` denominator
**and** in the `cells` record that feeds the McNemar / paired-difference
statistics. The observed symptom was `context_dump` printing adherence 0.00 at
N=150 when the truth was that the gateway rejected every prompt at that size —
an **infrastructure failure reported as a behavioural failure**, exactly the
artefact a hostile reviewer looks for.

## The correction

Generic-error cells are now excluded from the crossover's adherence numerator,
denominator, and paired `cells` record **exactly like CWE cells**. Only
genuinely answered cells are `attempted`; when none were, `adherence_rate` is
`None` rather than a misleading 0.0.

Each crossover curve point now carries always-present coverage fields
alongside the existing `context_window_exceeded_*`:

- `attempted` — cells that produced a scored answer (`total − cwe − errors`);
- `error_count`, `error_rate` — generic-error cells at this (arm, N).

The dataset's `errors` list and each sidecar cell record now tag every failure
with a **kind**, classified by exception type at the catch site (no string
matching): `context_window_exceeded | schema | gateway | transport | error`
(see `providers.answering.error_kind`). Reports and the dashboard flag a
partial-coverage curve cell with `*`.

## Scope and non-effects

- **No gold labels, scoring rubric, or gate changed.** A cell that genuinely
  answered and got it wrong is still `adherent=False` and still counts — only
  cells that never produced an answer are excluded.
- **Confirmatory tests (Amendment 1) are unaffected in intent** and become
  more faithful to their stated "over completed cells" definition: the H1
  `rac` vs `naive_rag` paired analysis now never sees a fabricated
  non-adherent outcome from an infrastructure failure.
- **Resume policy unchanged.** Only CWE cells replay from a `.partial.jsonl`
  sidecar (a deterministic structural outcome); every generic-error kind is
  re-run on `--resume`, since recovering transient failures is the point of
  resuming.
- **Backward compatible.** The new point fields are additive; older datasets
  lacking them read through `.get` defaults in every consumer.
