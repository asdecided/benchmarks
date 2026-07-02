---
schema_version: 1
id: AQA-KWGQJ4PHZE3H
type: design
---
# Harness Architecture: Contracts In, Evidence Out

## Context

The benchmark must be runnable by anyone, against any autonomous-QA agent,
and its numbers must survive scrutiny. That forces every load-bearing piece —
corpus access, agent invocation, token metering, scoring — onto published,
inspectable seams (AQA-KWGQJ4B7MDRK).

## User Need

A benchmark operator needs one command per concern: list the apps, run an
agent over an app's capabilities, re-score recordings for free, and render
the results page. An agent vendor needs a narrow, documented seam to plug
their agent in. A skeptic needs to re-derive every published verdict from
recorded evidence.

## Design

Four stdlib-only Python packages behind one CLI (`runner.cli`):

- **apps** — each frozen app is a directory with an `app.json` manifest
  (modality, serve command, readiness, capability expectations) and a seeded
  `rac/` corpus. The harness treats manifests as data; there are no
  app-specific branches.
- **agents** — the seam. `AgentAdapter.build(RunSpec)` produces a subprocess
  invocation of the agent's published CLI; `AgentAdapter.parse(stdout,
  exit_code)` is a pure function from raw evidence to a typed outcome. The
  reference adapter shells the pinned `@itsthelore/proofkeeper` package by
  real path from `workspace/`.
- **runner** — orchestrates a run: export the corpus over
  `rac export --graph`, start the app on a fresh port, start the model
  proxy, invoke the agent, and write an append-only record carrying the
  exact config, raw stdout/exit code, metered usage, and wall-clock.
- **scoring** — re-derives verdicts from records with the same pure parser,
  scores honesty against the seeded expectations, aggregates by app,
  modality, model, and tier, computes run-to-run variance for repeated
  configs, and renders the Markdown and HTML results pages.

The model proxy is one component with two modes on the agent's documented
BYOK seam (`OPENAI_BASE_URL`): **forward** meters real provider traffic per
call; **scripted** replays a canned per-capability flow — the stub model that
lets CI run the whole pipeline with no key (AQA-KWGQJ50NF3AX).

## Constraints

No engine or agent internals may be imported (ADR-092/ADR-063 lineage);
scoring must be deterministic with no embeddings and no LLM judge
(ADR-066 lineage; AQA-KWGQJ5AD2PE0); apps freeze on publication; results
are append-only; the core spine runs on the Python standard library alone.

## Rationale

Subprocess-and-parse is the only integration shape every future agent can
meet, and pure-function parsing is what makes recorded results re-scorable
for free. Riding the BYOK base-URL seam gives token metering and the CI stub
through one mechanism, without touching any agent's code.

## Related Requirements

- AQA-KWGQJ4B7MDRK

## Related Decisions

- AQA-KWGQJ50NF3AX
- AQA-KWGQJ5AD2PE0
