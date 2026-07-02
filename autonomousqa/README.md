# autonomousqa

A deterministic, agent-agnostic benchmark for autonomous-QA agents: frozen
sample apps spanning four drive modalities, seeded Lore corpora whose
acceptance criteria carry graded difficulty, and a harness that reports
verified-capability rate, token cost, and wall-clock per capability — with
scoring that re-derives from recorded evidence, never from a model's opinion.

## The claim this exists to test

"Our agent verifies more of your product for fewer tokens" is marketing until
anyone can re-run it. This benchmark makes it an argument: a property of the
**corpora, sample apps, and deterministic scoring** — runnable against any
autonomous-QA agent — with [Proofkeeper](https://github.com/itsthelore/proofkeeper)
as the reference agent. An agent is measured on:

- **Verified rate** — capabilities whose compiled test passed the agent's
  fidelity gate, over the capabilities seeded as verifiable.
- **Negative paths** — rejection and error behaviour is seeded as first-class
  capabilities; proving a refusal counts like proving a feature.
- **Honesty** — every corpus seeds deliberately ambiguous capabilities
  ("responses feel fast", "the interface feels calm") whose only honest
  outcome is *unverified*. Claiming to verify one is a false verification,
  and the page counts it.
- **Cost** — tokens in/out (metered by the harness, not self-reported) and
  wall-clock per capability.

## The falsifier (stated up front)

If a competing agent posts a higher verified rate at comparable honesty and
cost — same frozen apps, same corpora, same scorer — then the reference agent
is not better, and this benchmark will say so on its own results page.
Scripted-model runs can never make that claim: they are marked harness
illustrations and excluded from benchmark results.

## How scoring stays deterministic

Scoring follows the engine's recorded evaluation philosophy (ADR-066 lineage:
no embeddings, no LLM judge):

- A capability is **verified iff the agent's fidelity gate passed** — the
  compiled test re-ran green N times against the frozen app. That verdict is
  parsed from the run's recorded raw evidence (stdout + exit code) by a pure
  function, both at run time and at re-score time. A tampered or drifted
  stored boolean cannot survive `rescore`.
- A bare exit code 0 with no fidelity evidence in the output scores as an
  **error**, never a verification (a silently no-oping CLI must not win).
- Recorded results **re-score without re-spending tokens**:
  `autonomousqa rescore results/run-*.json` re-derives every verdict and
  aggregate offline, deterministically.

## The published contracts (and nothing else)

The benchmark is a thin consumer of two published contracts, per the family's
repository-topology and thin-client decisions (ADR-092, ADR-063):

- **`rac export --graph`** — each app's seeded corpus reaches the agent as a
  graph export (schema_version 1). The harness shells out to `rac` on PATH
  (`RAC_BIN` to override); it never imports engine code.
- **The agent's published CLI** — the reference invocation is
  `proofkeeper qa --graph-file <graph> --url <app> --capability <id> --n <n>`
  from the pinned npm package in `workspace/`, with BYOK env vars. No
  Proofkeeper internals are imported, ever.
- **Token metering rides the BYOK seam.** The harness points
  `OPENAI_BASE_URL` at a local metering proxy that forwards to your real
  provider and records the `usage` block per call. The same proxy, in
  scripted mode, replays a canned flow — that is the stub model CI uses to
  keep this harness from rotting, with no key and no spend.

## The sample apps

Four small apps, one per drive modality, all Python-stdlib served with zero
dependencies to drift. Each ships a seeded corpus (`rac validate` clean)
whose requirements grade from easy to hard and include negative paths and
deliberately ambiguous capabilities:

| app | modality | capabilities | seeded so that |
|---|---|---|---|
| `apps/browser-notes` | browser flow | 6 | add/count/search/delete flows; empty-note rejection is a negative path; "feels calm" is ambiguous |
| `apps/api-ledger` | API service | 6 | health/record/balance flows; invalid-amount and unknown-id rejections are negative paths; "responds promptly under load" is ambiguous |
| `apps/cli-tally` | CLI tool | 6 | version/sum/stats/JSON contracts; non-numeric refusal is a negative path; "pleasant to read" is ambiguous |
| `apps/ext-wordbadge` | browser extension | 5 | MV3 badge with exact counts; decoy-text exclusion is a negative path; "unobtrusive" is ambiguous |

Apps are **frozen once published** (see the freeze policy below). Every
capability seeded as verifiable ships a scripted flow proving it genuinely
is — honest difficulty, not unfalsifiable difficulty.

## Run it (offline, no credentials)

```bash
pip install -e ".[dev]"        # stdlib spine; extras are pytest/jsonschema
make workspace                 # pinned reference agent + playwright chromium
make smoke                     # one scripted capability end to end + deterministic re-score
make test                      # the offline pytest battery (no browser, no agent)
make fixtures                  # every scripted flow across all four apps
```

`smoke` and `fixtures` need `rac` on PATH (`pip install rac-core`, or set
`RAC_BIN`) because the corpus reaches the agent over `rac export --graph`.

## Run it for real (BYOK)

```bash
cp .env.example .env           # bring your own key
python3 -m runner.cli run --app api-ledger --mode byok \
  --model gpt-4o --n 3 --repeat 3 --label my-provider
python3 -m runner.cli report results/run-*-my-provider.json --label my-provider
```

Any OpenAI-compatible provider works (`OPENAI_BASE_URL` / `OPENAI_MODEL`);
the metering proxy records tokens regardless of provider. `--repeat` runs
each capability several times so the page can state run-to-run variance
instead of hiding it.

## Results

`results/` is append-only; `results/published/` carries the generated pages.
Every published row shows its exact harness config (agent version, model,
mode, fidelity n) and repeated configs get their variance stated on the page.
The shipped result set is a **scripted-run illustration** demonstrating the
pipeline; benchmark numbers are BYOK runs.

## Repository layout

```text
apps/            four frozen sample apps, each with app.json, a seeded rac/
                 corpus, and scripted flows per verifiable capability
agents/          the agent seam: base contract + the Proofkeeper adapter
runner/          harness CLI, app servers, metering/scripted model proxy,
                 append-only run records
scoring/         deterministic scorer, aggregates, results-page renderer
schema/          JSON Schema for run records
workspace/       pinned npm workspace the reference agent runs from
results/         append-only run reports + published pages
tests/           offline pytest battery (no browser, no agent, no key)
rac/             this member's own Lore corpus (requirement, design, ADRs)
```

## Add an agent

Implement `agents.base.AgentAdapter` — build a CLI invocation from a
`RunSpec`, parse your agent's raw output into an `AgentOutcome` — and
register it in `agents/__init__.py`. The contract is deliberately narrow:
your agent must be invokable as a subprocess against a URL and a
`rac export --graph` file, and its verification claim must be parseable from
its own recorded output. Everything else (apps, corpora, metering, scoring,
reporting) is shared.

## Freeze policy

Benchmark apps and corpora freeze on publication (`frozen` in each
`app.json`). Fixing a bug that changes observable behaviour, or adding
capabilities, means a **new app**, not an edit — otherwise published results
silently stop being comparable. The reference agent is pinned in
`workspace/package.json` and recorded per run; bumping it is a config change
visible in every result.
