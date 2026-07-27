# Agentic benchmark run — handoff

The real, funded benchmark run is meant to be executed by a **fresh Claude Code
session** (e.g. once LiteLLM routing to Anthropic is set up), separate from
wherever the harness was built. This document is the self-contained brief for that
session.

## How to use

1. Start a Claude Code session with the `asdecided/benchmarks` repository
   in scope. The benchmark lives in its `decisiongrounding/` subdirectory (the
   standalone `itsthelore/decisiongrounding` repo was archived into it, history
   preserved); every command below runs from that subdirectory.
2. Export your credentials (see the prompt) — for a LiteLLM/proxy run, set
   `ANTHROPIC_BASE_URL` and the virtual key.
3. Paste the prompt block below as your first message and let the session drive.

It assumes no prior context: it reads `CLAUDE.md`, `README.md`, and
`CONTRIBUTING.md` itself, probes the endpoint before spending, validates cheaply,
then runs the headline compare and the multi-seed crossover, generates the report,
preserves the artifacts, and opens a data-provision PR — honouring the project's
credibility and attribution rules.

Everything the prompt references is already on `main`: the `compare`/`batch`/`demo`
runners, multi-seed `--seeds`/`--augment` with mean ± CI and the paired
`rac − naive_rag` difference, confidence bands in the charts/dashboard/report, the
`scripts/litellm_probe.py` endpoint probe, `scripts/run_real.sh` (with `BATCH` and
`SEEDS`), `scripts/from_source.sh` (venv + install + keys + run from a fresh
clone), and the `paper/` LaTeX scaffold + `scripts/paper_figs.py`.

---

```text
You are Claude Code working on the asdecided/benchmarks repository. The
benchmark is its decisiongrounding/ subdirectory — treat that directory as your
working directory for every command below. It is a
reproducible benchmark testing whether deterministic, supersession-aware
decision-grounding makes a coding agent follow prior decisions better than
context-dump, naive RAG, or no grounding, reported as an adherence-vs-N crossover
with token cost. Before doing anything, read CLAUDE.md, README.md (especially the
"Run it for real" and "Through a proxy (LiteLLM)" sections), and CONTRIBUTING.md
(the credibility rules are binding).

## Goal
Produce BOTH of SWE-DecisionBench's pre-registered co-primary results
(spec/analysis-plan-amendment-1.md), generate the report, preserve the
artifacts, and open a data-provision PR:
- Part A — the real adherence-vs-N crossover (the discriminating
  rac-vs-naive_rag result; H1), over the 49-scenario study-grade roster.
- Part B — the decision-conditioned resolution outcome (H2): the GitChameleon
  evidence run in ../gitchameleon/, scored by the upstream harness.
A real base-N headline compare already exists —
results/published/2026-06-20-headline-opus-4-8-voyage.md (grounding decisive at
0.95 vs 0.00 over the original 19 scenarios; all grounding arms tie at base N,
as designed) — but it predates the scaled roster, so Step 3's re-run IS needed
this time. The harness, multi-seed variance, paired McNemar/effect-size
statistics, batch mode, report generator, dashboard, and paper scaffold are all
on main and tested — this run produces the numbers.

## Environment (LiteLLM routing)
Both LiteLLM surfaces are supported; probe tells you which one you have (Step 1).
- Anthropic-native passthrough (/v1/messages proxied): the `anthropic` SDK
  honours ANTHROPIC_BASE_URL — run with --answering claude as normal. Set:
    export ANTHROPIC_BASE_URL=<litellm endpoint, Anthropic-native route>
    export ANTHROPIC_API_KEY=<litellm virtual key>
- OpenAI-compatible only (/chat/completions): use the litellm backend —
  --answering litellm:<model-alias> (or ANSWERING=litellm:<alias> for
  run_real.sh). Same scaffold/prompt/schema as the claude backend; synchronous
  only (no --batch). Set:
    export LITELLM_BASE_URL=<litellm endpoint, OpenAI-compatible root>
    export LITELLM_API_KEY=<litellm virtual key>
Either way:
  export VOYAGE_API_KEY=<voyage key>            # strong embeddings for naive_rag

## Step 0 — branch & install
- Work on a NEW branch off fresh origin/main: claude/decision-grounding-results-<slug>.
  Never push to main.
- Install: `pip install -e ".[real,schema,chart]"`. The `rac` arm needs the `rac`
  CLI on PATH (`brew install asdecided/tap/asdecided-core`, then
  `export DECIDED_BIN=decided`). Alternatively `./scripts/from_source.sh` does venv + install + loads
  keys from .env + probe + run in one go; the granular steps below are recommended
  for the first real run so you can inspect each stage.

## Step 1 — PROBE the proxy FIRST (tiny spend)
Run: python -m scripts.litellm_probe
It reuses the exact request the benchmark sends and prints a verdict on
(1) messages.create + structured outputs + usage, and (2) the Batch API.
- Both pass  -> Anthropic passthrough: proceed and use --batch.
- Structured outputs FAIL -> it's an OpenAI-compatible gateway, NOT a passthrough.
  Re-probe that surface:  python -m scripts.litellm_probe --mode openai --model <alias>
  If it passes, run everything with --answering litellm:<alias> (synchronous
  only — skip --batch/BATCH=1 and Step 3's `batch` variant). If BOTH modes fail,
  STOP and tell the maintainer: the gateway blocks schema-enforced JSON and
  scoring needs it; do not hack around it with free-text parsing.
- Batch FAILS but structured outputs pass -> run synchronously (drop --batch);
  reserve batch for a direct Anthropic key.
Model identity: with --answering claude confirm the proxy's alias maps to EXACTLY
claude-opus-4-8 (the report records that as the version). With litellm:<alias>
the report records the spec string itself — confirm the alias is pinned to a
fixed model on the gateway (not "latest"), or the run isn't reproducible.

## Step 2 — cheap validation before the full spend
python -m runner.cli demo --scenarios scenarios_real \
  --arms naive_rag,no_grounding,rac --distractors real --ns 10 --seeds 0-1 \
  --answering claude --embedder voyage:voyage-4-large [--batch]
Confirm real usage is recorded, the dataset is green, the .partial.jsonl sidecar
streams, each curve point carries adherence_rate_ci / _values, AND the dataset
carries the per-cell `cells` list with a populated `stats` block (per-N exact
McNemar + effect sizes — the pre-registered analysis). Report the observed
per-cell token cost so the full run can be estimated.

## Step 3 — headline base-N compare (all arms, full 49-scenario roster)
The committed seed-0 headline covers only the original 19 scenarios; the scaled
roster (49 scenarios incl. 5 negative controls) needs a fresh base-N compare:
python -m runner.cli compare --scenarios scenarios_real \
  --arms context_dump,naive_rag,no_grounding,rac \
  --answering claude --embedder voyage:voyage-4-large --seed 0
(use `batch` instead of `compare` if the Batch API is available)
The run report now carries a `stats` block (paired by scenario); check the
rac-vs-no_grounding McNemar is populated and sane before proceeding.

## Step 4 — the real crossover with error bars
Thesis arms only for the sweep (context_dump's curve comes free from the offline
--cost-curve; paying its ~1.5M tokens/cell at N=300 isn't worth it). The sweep
covers the 44 discriminating scenarios (negative controls are base-N only), so
budget ~2.3x the old 19-scenario estimates:
  SEEDS=0-4 BATCH=1 CROSSOVER=1 ARMS=naive_rag,no_grounding,rac \
    NS=10,50,150,300 ./scripts/run_real.sh
This yields mean ± 95% CI per point, the paired rac−naive_rag difference + CI,
and dataset["stats"] — per-N exact McNemar + risk difference + odds ratio over
the scenario × seed pairs. The CONFIRMATORY statistic is the rac-vs-naive_rag
McNemar at N=300 (alpha 0.05, per the amendment); the paired CI remains the
supporting variance evidence. If the confirmatory cell is degenerate or the CI
straddles 0 at N>=50, add seeds only at those N via:
python -m runner.cli demo ... --augment <crossover_dataset.json> --seeds 0-9
(this re-runs only the new seeds and re-aggregates cells + stats).

## Part B — the decision-conditioned resolution outcome (H2, ../gitchameleon/)
Work in ../gitchameleon/ (same repo). Every step is resumable; see its README
"The funded run" for the full commands.
1. python3 fetch_dataset.py   (records the dataset revision pin in
   dataset/provenance.json — the paper cites it)
2. python3 build_corpus.py    (per-example version-pin decision corpora)
3. python3 run.py --dry-run   (bundles; prompts never restate the pin)
4. python3 run.py solutions --bundles out/bundles.jsonl --answering claude \
     --seed 0 --out out/solutions
   (arms no_grounding,rac; naive_rag additionally needs its embedder pinned —
   if you pin one, record it. litellm:<alias> works for OpenAI-compatible
   gateways; offline-stub is the keyless plumbing check.)
5. Clone github.com/mrcabbage972/GitChameleonBenchmark at a COMMIT YOU RECORD,
   run its `make evals-setup`, then per arm:
     evaluate --solution-path out/solutions/solutions-<arm>.jsonl
   (Docker; the per-version dependency installs are the slow part — budget
   hours, not minutes. Its executable tests are the scorer; we add none.)
6. python3 run.py score --arm <arm> --eval-results \
     out/solutions/solutions-<arm>_eval_results.csv \
     --answering-model <pin> --upstream-harness <commit> \
     --out out/resolution_records.jsonl [--append]
   then: python3 run.py stats --records out/resolution_records.jsonl
7. Preserve out/resolution_records.jsonl + the stats JSON + per-arm pass rates
   under gitchameleon/results/published/ with the dataset revision, model pin,
   and upstream-harness commit. These numbers are an arm comparison under the
   no-version-in-prompt protocol — NOT comparable to the upstream leaderboard;
   say so wherever they appear.

## Step 5 — report + preserve (results/ is APPEND-ONLY; never edit prior runs)
- python -m scripts.report --run results/run-*-compare-*.json \
    --crossover <crossover_dataset.json> --cost-curve \
    --resolution ../gitchameleon/out/resolution_records.jsonl \
    --out results/published/decision-grounding-report.md
  (use the run-*-batch-*.json file if you ran via the Batch API; --resolution
  renders the co-primary resolution section — omit it only if Part B is still
  pending, and say so in the PR)
- python -m scripts.dashboard --run <compare.json> --crossover <crossover.json> \
    --cost-curve --out results/published/index.html
- Paper figures + fill: `make paper-figs CROSSOVER=<crossover.json>` (PDF with the
  [chart] extra, else SVG; also writes paper/figures/stats_table.tex — the paper
  \inputs it, so the statistics regenerate from the dataset), then fill the
  \todo placeholders in paper/sections/* (result sentence in abstract.tex, the
  verdicts in results.tex/discussion.tex — BOTH outcomes — and the confirmed
  pins in setup.tex). NOTE: line_chart already accepts bands=, but
  scripts/paper_figs.py does not yet pass them — wiring CI bands into the paper
  figures (matplotlib fill_between + the SVG fallback) is a small remaining
  follow-up; do it here so the paper figures match the dashboard.
- Preserve the dataset + report + charts under results/published/ (and the
  Part B records under ../gitchameleon/results/published/).

## Step 6 — open the data-provision PR
- Commit with the maintainer identity on BOTH author and committer
  (Tom Ballard <tom@armytage.co>), format `type(area): summary [roadmap:decision-grounding]`,
  and NO tool attribution (no Co-Authored-By, no "Generated with/by Claude Code",
  no claude.ai/code link).
- Open the PR into main. IMPORTANT: mcp__github__create_pull_request auto-appends a
  "_Generated by Claude Code_" footer — immediately call
  mcp__github__update_pull_request with the same body to strip it (update does NOT
  re-append), then read the PR body back to verify it's clean.
- Subscribe to the PR and drive CI to green. The benchmark's CI lives at the
  repo root — .github/workflows/decisiongrounding-ci.yml (test matrix, offline
  demo smoke, rac corpus gate), path-filtered to decisiongrounding/** — plus the
  per-tool suite's workflow if your diff touches shared paths.

## Honesty / credibility (non-negotiable — CONTRIBUTING.md + the amendment)
- The verdicts are computed from the numbers, per outcome. H1 falsified if the
  rac-vs-naive_rag exact McNemar at N=300 is not significant (grounded ≈
  naive_rag); H2 falsified if rac does not beat no_grounding on upstream pass
  rate. A MIXED result (one holds, the other doesn't) is pre-declared
  publishable — report it plainly. Do not spin. The dashboard/report already
  derive the adherence verdict from the paired statistics; do not override it.
- Gold labels were authored blind; spec/taxonomy/rubric and the analysis-plan
  amendment are frozen — do not change them to fit the result.
- Note in the report that the run was proxied via LiteLLM (ANTHROPIC_BASE_URL) and
  that £/$ figures are Anthropic list-price estimates, not the proxy's billing.
- Rotate any API key shared in plaintext.

## Gates before pushing
- python -m pytest -q  green
- rac gate rac  green (validate + relationships + review)
- CI green on the PR

When done, report: the paired rac−naive_rag difference + CI at each N; the
exact McNemar p (and b/c counts) per arm pair at each N, naming the
confirmatory N=300 cell; the per-arm GitChameleon pass rates with their paired
tests; both falsifier outcomes (H1 / H2: supported / not supported / mixed);
and the per-arm token cost.
```
