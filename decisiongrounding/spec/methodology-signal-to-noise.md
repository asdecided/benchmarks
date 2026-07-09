# Methodology — signal-to-noise and scenario health

*Additive methodology note (not a pre-registration amendment). It documents how
the reporting layer separates signal from noise; it changes no gold labels, no
scoring rubric, and none of the confirmatory tests in
`analysis-plan-amendment-1.md` / `-2.md` (both frozen).*

## Why

Two analyses of coding/LM evaluations converge on the same warning:

- OpenAI, *["Separating signal from noise in coding evaluations"](https://openai.com/index/separating-signal-from-noise-coding-evaluations/)* — a
  widely-used benchmark was found to have ~20–30% of tasks broken (unsolvable,
  or verified against hidden assumptions), so failures reflected the harness,
  not the model. A trustworthy eval must (a) separate genuine model failures
  from harness/grading noise, and (b) know how many of its tasks actually carry
  signal.
- Ai2, *["Signal and Noise"](https://allenai.org/blog/signal-noise)* — a
  benchmark is only reliable when its **signal** (spread between systems) is
  large relative to its **noise** (run-to-run variance). They report a
  signal-to-noise ratio and select high-SNR subtasks.

This benchmark already avoids the largest noise source — grading — by scoring
structurally and deterministically (no LLM judge). This note adds the two
missing pieces: an explicit signal-to-noise ratio, and a per-scenario validity
audit.

## Signal-to-noise (SNR)

For an arm contrast `(a, b)` at corpus size `N`:

    signal = |mean over seeds of (adherence_a − adherence_b)|      # dataset["paired"][…]["diff_mean"]
    noise  = std  over seeds of (adherence_a − adherence_b)        # …["diff_std"]
    SNR    = signal / noise

The difference is taken **within each seed** (common random numbers), so `noise`
is the genuine seed-to-seed wobble of the *gap*, not of either arm alone.

- **SNR < 1** — the between-arm gap is smaller than the run-to-run noise:
  **noise-dominated**, not a result to lean on. Flagged with `*` in the report.
- **noise cannot be estimated from one seed.** With `n_seeds < 2` the report
  says "noise not estimable" and prints no ratio — the single most important
  honesty guard, and the direct lesson from both articles. Run `SEEDS=0-4`
  (`make real-crossover SEEDS=0-4`) to measure it.
- Edge cases: an identical nonzero gap every seed is `clean (σ=0)` (maximal
  signal); an identical zero gap every seed is `0 (tie)` (no effect).

Reported for both pre-registered contrasts: `rac`-vs-`naive_rag` (H1, the
falsifier) and `rac`-vs-`no_grounding` (H2, grounding vs the parametric-memory
floor). Headline SNR is quoted at the largest `N` — the buried-in-distractors
corpus size where the thesis is actually adjudicated. Implementation:
`scoring/snr.py`.

## Scenario health (discrimination / validity audit)

Each scenario is classified against the two control arms already in the sweep —
the ceiling (`context_dump`, sees the whole corpus) and the floor
(`no_grounding`, parametric memory only):

| class | condition | meaning |
|---|---|---|
| **broken** | ceiling never adheres at any N | likely mis-specified / unsolvable from the corpus |
| **contaminated** | floor adheres | answerable from pretraining memory — doesn't test grounding |
| **tie** | no arm separates from another at any N | degenerate, contributes no signal |
| **discriminating** | otherwise | grounding separates from the floor |
| **unknown** | neither control arm in the sweep | cannot audit |

The summary count ("X of Y discriminating") is this benchmark's analogue of
OpenAI's broken-task ceiling. Implementation: `scoring/health.py`.

## Contamination defense

Real PEPs/RFCs are in the answering model's pretraining, so it may "know" that
PEP 440 supersedes PEP 386 independent of the grounding it is given. Two
defenses, both already in the design and now surfaced:

1. **Synthetic scenarios are contamination-proof by construction** — the
   `scenarios/` bank invents fictional ADRs the model cannot have seen.
2. **The `no_grounding` floor detects contamination in the real scenarios** —
   if parametric memory alone adheres, the scenario is flagged `contaminated`
   by the health audit and its adherence is not evidence that grounding helped.

## Relationship to the confirmatory analysis

SNR and scenario health are **descriptive reporting**, computed from the same
`paired` / `per_scenario` data the frozen McNemar analysis already uses. They
add no hypothesis and change no gate: H1/H2 remain exactly as pre-registered in
amendment-1. They exist so a reader — or a hostile reviewer — can judge for
themselves whether a reported gap is signal or noise, and how much of the
roster is actually pulling its weight.
