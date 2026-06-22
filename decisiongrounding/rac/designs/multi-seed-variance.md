---
schema_version: 1
id: DG-KVPXS090VR5N
type: design
tags: [crossover, cli, statistics, charts]
---
# Multi-seed Crossover: Variance, Paired CIs, and Confidence Bands

## Context

Implements the variance-reporting decision (DG-KVPXSF1B0PW8) in the harness. Today
`scoring/crossover.py` builds a single-seed dataset; `runner/cli.py demo` drives it;
`runner/dashboard.py`, `scripts/report.py`, and `scripts/paper_figs.py` consume the
per-(arm, N) "point" dicts, and `scoring/charts.py line_chart` renders the curves.

## User Need

A reviewer (and the paper) needs the adherence-vs-N curve and the rac-vs-naive_rag
verdict to carry **error bars**, so a result is not an artefact of one lucky
distractor draw, and the falsifier can be judged statistically.

## Design

- **`--seeds` (crossover/`demo` only).** Accepts a spec: `"3"` (single), `"0,1,2"`
  (list), `"0-4"` (range), or combinations. Unset → today's single `--seed`
  behaviour, unchanged. Add `--augment <dataset.json>` to add only *new* seeds to
  an existing dataset and recompute.
- **`build_dataset_multiseed(...)`** loops seeds, calling the existing
  `build_dataset` / `build_dataset_batched` per seed (so batch and multi-seed
  compose), then merges per (arm, N):
  - keep `adherence_rate`, `governing_recall`, `token_estimate_mean`,
    `input_tokens_mean` as the **mean** (back-compat);
  - add `*_ci: [lo, hi]`, `*_std`, `*_values: [...]`, plus `n_seeds` and `seeds`.
  - `per_scenario` records become the adherent **fraction across seeds**.
- **Paired difference** `dataset["paired"]["rac_vs_naive_rag"] = [{N, diff_mean,
  diff_ci: [lo, hi], n}]`, differenced within each seed (common random numbers).
- **Stats in `scoring/metrics.py`** (reuses the file with `adherence_variance`):
  `t_critical_95(df)` (hardcoded table), `mean_ci(values)`, and `summarize(values)
  -> {mean, std, ci, n, values}`. No SciPy.
- **Confidence bands in `scoring/charts.py`:** `line_chart` gains
  `bands: dict[str, list[(x, lo, hi)]] | None`; each band is a low-opacity polygon
  rendered **inside the existing `<g class="series" data-arm=...>`** group so the
  legend toggle hides band and line together.
- **Consumers pass bands through** from the `_ci` fields and show `mean ±ci` in the
  curve tables (`runner/dashboard.py`, `scripts/report.py`); the head-to-head
  verdict uses the paired CI (falsifier triggered when the paired diff CI at
  N ≥ 50 includes or sits below zero). `scripts/paper_figs.py` band support and the
  paper's `setup.tex` follow once the paper branch (PR #5) merges.

## Constraints

- **Backward compatible:** existing point fields keep their meaning (the mean);
  only-additive new keys. Single-seed datasets render unchanged everywhere.
- **No new dependency**; deterministic, offline-capable.
- Bands must sit inside the `data-arm` group to preserve the existing
  legend-toggle behaviour.

## Rationale

Calling the existing single-seed builders per seed and merging keeps one source of
truth for a cell's computation and makes batch+multiseed compose for free. Storing
per-seed values makes `--augment` and the paired difference trivial.

## Alternatives

- Thread `seeds` through `build_dataset` internally rather than wrapping it.
  Rejected: the wrapper keeps the single-seed path pristine and testable.
- Store only summary stats (drop per-seed values). Rejected: kills append and the
  paired difference.

## Accessibility

Not a UI surface beyond the existing charts; bands use fill plus the existing
coloured line/marker, and the line itself remains, so the curve is not conveyed by
the band shading alone.

## Style Guidance

Reuse existing chart colours (`color_for`) at low opacity for bands; curve tables
render `mean ±half` compactly, consistent with current `_f` formatting.

## Open Questions

- Whether to extend `--seeds` to the base-N `compare` later (noted as a follow-up;
  out of scope here).

## Related Decisions

- DG-KVPXSF1B0PW8
- DG-KVMRV4YRMJB6
