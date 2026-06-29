# Agentic benchmark run — handoff

The real, funded benchmark run is meant to be executed by a **fresh Claude Code
session** (e.g. once LiteLLM routing to Anthropic is set up), separate from
wherever the harness was built. This document is the self-contained brief for that
session.

## How to use

1. Start a Claude Code session with the `itsthelore/decisiongrounding` repository
   in scope.
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
You are Claude Code working on the itsthelore/decisiongrounding repository — a
reproducible benchmark testing whether deterministic, supersession-aware
decision-grounding makes a coding agent follow prior decisions better than
context-dump, naive RAG, or no grounding, reported as an adherence-vs-N crossover
with token cost. Before doing anything, read CLAUDE.md, README.md (especially the
"Run it for real" and "Through a proxy (LiteLLM)" sections), and CONTRIBUTING.md
(the credibility rules are binding).

## Goal
Produce the FIRST real benchmark data through a LiteLLM-routed Anthropic endpoint,
generate the report, preserve the artifacts, and open a data-provision PR. The
harness, multi-seed variance, batch mode, report generator, dashboard, and paper
scaffold are all on main and tested — this run produces the numbers.

## Environment (LiteLLM routing)
The official `anthropic` SDK honours ANTHROPIC_BASE_URL, so no code change is
needed IF the proxy exposes Anthropic's native /v1/messages route. Set:
  export ANTHROPIC_BASE_URL=<litellm endpoint, Anthropic-native route>
  export ANTHROPIC_API_KEY=<litellm virtual key>
  export VOYAGE_API_KEY=<voyage key>            # strong embeddings for naive_rag

## Step 0 — branch & install
- Work on a NEW branch off fresh origin/main: claude/decision-grounding-results-<slug>.
  Never push to main.
- Install: `pip install -e ".[real,schema,chart]"`. The `rac` arm needs the `rac`
  CLI on PATH (pip install "git+https://github.com/itsthelore/rac-core.git" if
  absent). Alternatively `./scripts/from_source.sh` does venv + install + loads
  keys from .env + probe + run in one go; the granular steps below are recommended
  for the first real run so you can inspect each stage.

## Step 1 — PROBE the proxy FIRST (tiny spend)
Run: python -m scripts.litellm_probe
It reuses the exact request the benchmark sends and prints a verdict on
(1) messages.create + structured outputs + usage, and (2) the Batch API.
- Both pass  -> Anthropic passthrough: proceed and use --batch.
- Structured outputs FAIL -> it's an OpenAI-compatible gateway, NOT a passthrough.
  STOP and tell the maintainer: the native code (output_config + Batch API) needs
  an OpenAI-client answering adapter; do not hack around it.
- Batch FAILS but structured outputs pass -> run synchronously (drop --batch);
  reserve batch for a direct Anthropic key.
Also confirm the proxy's model alias maps to EXACTLY claude-opus-4-8 (the report
records that as the version); if it routes elsewhere, fix the alias or note it.

## Step 2 — cheap validation before the full spend
python -m runner.cli demo --scenarios scenarios_real \
  --arms naive_rag,no_grounding,rac --distractors real --ns 10 --seeds 0-1 \
  --answering claude --embedder voyage:voyage-4-large [--batch]
Confirm real usage is recorded, the dataset is green, the .partial.jsonl sidecar
streams, and each curve point carries adherence_rate_ci / _values. Report the
observed per-cell token cost so the full run can be estimated.

## Step 3 — headline base-N compare (all arms, once)
python -m runner.cli compare --scenarios scenarios_real \
  --arms context_dump,naive_rag,no_grounding,rac \
  --answering claude --embedder voyage:voyage-4-large --seed 0
(use `batch` instead of `compare` if the Batch API is available)

## Step 4 — the real crossover with error bars
Thesis arms only for the sweep (context_dump's curve comes free from the offline
--cost-curve; paying its ~1.5M tokens/cell at N=300 isn't worth it):
  SEEDS=0-4 BATCH=1 CROSSOVER=1 ARMS=naive_rag,no_grounding,rac \
    NS=10,50,150,300 ./scripts/run_real.sh
This yields mean ± 95% CI per point and the paired rac−naive_rag difference + CI
(the falsifier statistic). If the paired CI at N>=50 straddles 0, add seeds only at
those N via:  python -m runner.cli demo ... --augment <crossover_dataset.json>
--seeds 0-9   (this re-runs only the new seeds and re-aggregates).

## Step 5 — report + preserve (results/ is APPEND-ONLY; never edit prior runs)
- python -m scripts.report --run results/run-*-compare-*.json \
    --crossover <crossover_dataset.json> --cost-curve \
    --out results/published/decision-grounding-report.md
  (use the run-*-batch-*.json file if you ran via the Batch API)
- python -m scripts.dashboard --run <compare.json> --crossover <crossover.json> \
    --cost-curve --out results/published/index.html
- Paper figures + fill: `make paper-figs CROSSOVER=<crossover.json>` (PDF with the
  [chart] extra, else SVG), then fill the \todo placeholders in paper/sections/*
  (result sentence in abstract.tex, the verdict in results.tex/discussion.tex,
  model/embedder/seed/scenario counts in setup.tex). NOTE: line_chart already
  accepts bands=, but scripts/paper_figs.py does not yet pass them — wiring CI
  bands into the paper figures (matplotlib fill_between + the SVG fallback) is a
  small remaining follow-up; do it here so the paper figures match the dashboard.
- Preserve the dataset + report + charts under results/published/.

## Step 6 — open the data-provision PR
- Commit with the maintainer identity on BOTH author and committer
  (Tom Ballard <tom@armytage.co>), format `type(area): summary [roadmap:decision-grounding]`,
  and NO tool attribution (no Co-Authored-By, no "Generated with/by Claude Code",
  no claude.ai/code link).
- Open the PR into main. IMPORTANT: mcp__github__create_pull_request auto-appends a
  "_Generated by Claude Code_" footer — immediately call
  mcp__github__update_pull_request with the same body to strip it (update does NOT
  re-append), then read the PR body back to verify it's clean.
- Subscribe to the PR and drive CI to green (the test matrix + the `rac corpus
  gate` job both run).

## Honesty / credibility (non-negotiable — CONTRIBUTING.md)
- The verdict is computed from the numbers. If naive_rag does NOT decay (grounded ≈
  naive_rag at N>=50), the falsifier is triggered — say so plainly and publish the
  losing result. Do not spin. The dashboard/report already derive the verdict from
  the paired CI; do not override it.
- Gold labels were authored blind; spec/taxonomy/rubric are frozen — do not change
  them to fit the result.
- Note in the report that the run was proxied via LiteLLM (ANTHROPIC_BASE_URL) and
  that £/$ figures are Anthropic list-price estimates, not the proxy's billing.
- Rotate any API key shared in plaintext.

## Gates before pushing
- python -m pytest -q  green
- rac gate rac  green (validate + relationships + review)
- CI green on the PR

When done, report: the paired rac−naive_rag difference + CI at each N, the
falsifier outcome (supported / not supported), and the per-arm token cost.
```
