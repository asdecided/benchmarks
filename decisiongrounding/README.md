# decisiongrounding

A reproducible benchmark that answers one question:

> Does a deterministic decision-grounding layer make a coding agent adhere to a
> team's **prior decisions** better than (a) dumping all the decision docs into
> context, (b) commodity RAG over the same docs, or (c) a general-purpose memory
> layer — and at what corpus size does any difference appear?

It is a **standalone** project. It does not depend on, or import, any specific
grounding implementation; the layer under test is just one arm behind a uniform
adapter.

## The objection this exists to test

> "Frontier models plus long context just absorb the decisions, so a persistence
> layer adds no durable value."

That objection is correct often enough that a benchmark which cannot reproduce
it is worthless marketing. So the threatening baselines are **mandatory**, not
courtesy arms:

- **`context_dump`** — paste every artifact into the answering model's context.
  This is the skeptic's position, implemented faithfully.
- **`naive_rag`** — embeddings + top-k over the same markdown. No typing, no
  relationship traversal.

A grounding layer earns its keep only by beating these — on the scenario types
where it should, at the corpus sizes where it should.

## The falsifier (stated up front)

**If the typed/grounded arm ≈ `naive_rag` on superseded + prohibition scenarios
at N ≥ 50, the retrieval thesis is dead.** We publish that result if we find it.
The benchmark is designed to be able to embarrass its sponsor; see
`CONTRIBUTING.md` ("publish losing results").

## How the comparison is kept fair

- **Held-constant answering model.** Every arm feeds context to the *same fixed
  answering model* with the *same prompt scaffold*, pinned by model + version +
  temperature + seed. Arms differ **only** in how they select and assemble the
  grounding context.
- **Symmetric grounding injection.** Each arm gets one equal opportunity to
  populate the answering model's context: `context_dump` supplies everything,
  `naive_rag` supplies its top-k, the grounded arm supplies its typed retrieval.
- **Deterministic scoring first.** Adherence is scored by structural inspection
  of the agent's proposed change (did it propose the prohibited migration? did it
  follow the superseded decision?). An LLM judge is a disclosed, unbuilt fallback
  — see `spec/scoring-rubric.md`.

### Symmetric-injection caveat (read this)

This benchmark isolates **retrieval/assembly quality**: given one symmetric shot
at the context window, which assembly strategy yields better decision-adherence?
It does **not** test whether a pull-based MCP grounding layer actually *gets
consulted* in production — whether an agent invokes the tool at the right moment
is a separate deployment question, out of scope here. Reading a favourable result
as "this layer will fix adherence in production" overstates what was measured.

## Headline metric and artifact

- **Headline metric:** decision-adherence rate.
- **Headline artifact:** an adherence-vs-corpus-size curve over
  N ∈ {10, 50, 150, 300} with rising conflict density — the story is the
  crossover point.
- Also reported: stale-decision rate, false-permit / false-prohibit rate,
  per-arm run-to-run variance, and **governing-decision recall** — did the arm's
  grounding actually contain the binding decision? Recall is the mechanistic
  explanation for why adherence moves (the analog of MemoryBench's Hit@K). There
  is deliberately **no** composite score.

## Related work

**SWE-ContextBench** (Zhu et al., 2026; [arXiv:2602.08316](https://arxiv.org/abs/2602.08316))
is the closest neighbour. It finds that *accurately retrieved and summarised* prior
context improves coding-agent resolution accuracy and cuts runtime and token cost, while
*unfiltered or wrongly-selected* context gives limited or **negative** benefit. That is the
same gradient this benchmark's `context_dump → naive_rag → rac` arms exist to measure, and
it treats **token cost** as a first-class metric, as we do. We read its result as external
support for the premise — and as a sharpener for where our distinct contribution must lie.

Our niche is deliberately narrower:

- **Durable decisions, not episodic experience.** SWE-ContextBench reuses prior *task*
  solutions (related GitHub issues/PRs) — "have I solved a similar problem before?". We
  test adherence to long-lived *governing decisions* (ADR- and standard-like) — "does a
  recorded decision forbid what I am about to do?".
- **Supersession is the discriminating signal.** Our headline case is *machine-stated*
  supersession (PEP 386→440, RFC `Obsoletes`): follow the live decision and drop the
  superseded one. Generic retrieval is necessary but not sufficient there — which is exactly
  where our [falsifier](#the-falsifier-stated-up-front) is aimed. If accurate retrieval
  alone closed the gap, the interesting result is the *stale/prohibited* case, not generic
  recall.
- **Deterministic, structural scoring** (ADR-066) — no embeddings, no LLM judge — over a
  **single-variable A/B**: one held-constant answering model and scaffold, varying *only*
  the grounding assembly. Cheaper and more reproducible than end-to-end resolution accuracy,
  at the cost of a narrower question (decision adherence, not "does the patch pass tests").

(See also MemoryBench's Hit@K, the analog of our governing-decision recall.)

## Run it (offline, no credentials)

```bash
cd decisiongrounding
make demo          # == python -m runner.cli demo
```

This runs the two real arms (`context_dump`, `naive_rag`) on the four worked
scenarios with a deterministic **offline** answering model, writes an
append-only report under `results/`, and emits the crossover chart
(`results/crossover.svg`, or `.png` with the `[chart]` extra).

> The offline answering model is a deterministic stand-in so the spine runs with
> zero credentials. **Its output is a harness illustration, NOT a benchmark
> result.** Real runs swap in the pinned Claude answering model and a real
> embedding backend (`pip install -e .[real]`) on real/public-derived corpora.
> See `rac/decisions/ADR-0001-harness-foundation.md`.

### Run it for real (pinned model + real retrieval)

**Quickest from a fresh clone** — one launcher creates a venv, installs the real
backends, loads your keys from `.env`, and runs (it probes the endpoint first if
you point `ANTHROPIC_BASE_URL` at a proxy):

```bash
cp .env.example .env        # then add ANTHROPIC_API_KEY (+ VOYAGE_API_KEY)
./scripts/from_source.sh                       # headline compare (all arms)
CROSSOVER=1 BATCH=1 ./scripts/from_source.sh   # + the adherence-vs-N curve, batched
```

Or set it up by hand:

```bash
pip install -e ".[real,schema,chart]"
export ANTHROPIC_API_KEY=...        # pinned answering model: claude-opus-4-8
export VOYAGE_API_KEY=...           # real embeddings for naive_rag

# stable rac arm additionally needs AsDecided Core's `decided` CLI on PATH
# (or set DECIDED_BIN)
python -m runner.cli compare \
  --arms context_dump,naive_rag,rac \
  --answering claude \
  --embedder voyage:voyage-4-large \
  --scenarios scenarios/ --seed 0
```

`naive_rag` embeds corpus sections with Voyage's `document` role and the task
with its `query` role, so the RAG baseline uses asymmetric query/document
embeddings the way Voyage intends — a fair, strong baseline, not a strawman.
The default Voyage model is `voyage-4-large` (Voyage's current flagship);
override with `--embedder voyage:<model>`. Each report records the embedder id +
dimension and the installed `anthropic`/`voyageai` versions (`backend_versions`)
so a run says exactly what produced it.

For repeat or large runs, `python -m runner.cli batch …` runs the same
comparison through the **Message Batches API at ~50% of standard token price**.
It assembles every arm's grounding locally (AsDecided Core, embeddings) up front, then
submits all answering calls as one batch and polls to completion (asynchronous —
usually under an hour). The trade vs `compare` is the live, abortable per-cell
feedback; for the first exploratory run prefer `compare`, for bulk runs prefer
`batch`. (`compare`/`run`/`demo` remain synchronous and streamed.)

A real run is expensive, so the runner protects your spend two ways. It
**preflights** the configuration before doing any work — a missing
`ANTHROPIC_API_KEY`, `VOYAGE_API_KEY`, backend package, or Core CLI fails fast
with an actionable message instead of part-way through a paid sweep. And it
**streams every completed run** to a durable `results/run-<stamp>-<label>.partial.jsonl`
sidecar as it lands; a transient API error on one (arm, scenario) cell is
recorded and skipped rather than discarding the cells already done (those errors
are also collected under `errors` in the final report, and a run with any error
exits non-zero).

The **crossover** can also run on the real backends:

```bash
# Real-model crossover. --ns keeps the API spend small (arms x scenarios x |ns|).
python -m runner.cli demo \
  --answering claude --embedder voyage:voyage-4-large --ns 10,50

# Repeat over several seeds for error bars: each curve point becomes mean +/- a
# 95% CI, and the rac-vs-naive_rag verdict is the paired difference's CI (the
# falsifier statistic). Cost multiplies with the seed count; --augment adds more
# seeds to an existing dataset without re-running the ones it already has.
python -m runner.cli demo --answering claude --embedder voyage:voyage-4-large \
  --ns 10,50 --seeds 0-4
```

This is where the thesis is actually tested — but note the boundary: with
`--answering claude` you get a real-*model* crossover **on the tiny synthetic
scenarios**. That is the plumbing for evidence, not the evidence. The real
result requires real/public-derived corpora (see CONTRIBUTING.md); until then
the crossover is plumbing, not evidence.

### Through a proxy (LiteLLM or any Anthropic gateway)

The answering model uses the official `anthropic` SDK, which honours the
**`ANTHROPIC_BASE_URL`** environment variable. So if your funded access routes
through a LiteLLM proxy (or any gateway) that exposes Anthropic's **native**
Messages route, no code change is needed — point the SDK at the proxy:

```bash
export ANTHROPIC_BASE_URL=https://your-litellm/...   # the Anthropic-native route
export ANTHROPIC_API_KEY=sk-litellm-virtual-key      # the proxy's virtual key
# then run compare / batch / demo exactly as above
```

The benchmark relies on three Anthropic-native features, so **probe the endpoint
first** (a couple of small calls) to confirm the proxy forwards them faithfully:

```bash
python -m scripts.litellm_probe        # reuses the exact request the run sends
```

It checks, and prints a verdict on:

1. **`messages.create` with structured outputs** (`output_config` + a JSON
   schema) — the response must parse back into a `ProposedChange`; this is what
   makes scoring deterministic. It also confirms token **`usage`** is reported
   (the cost report needs it).
2. **The Message Batches API** (`messages.batches`) — the `batch` /
   `make real-batch` / `demo --batch` path.

How to read the result:

- **Both pass** → it's a transparent Anthropic passthrough. Set the two env vars
  and run normally; `run_real.sh` prints the resolved endpoint so a proxied run
  is on the record.
- **Batch fails, structured outputs pass** → the proxy doesn't expose the batch
  endpoint. Run the crossover **synchronously** through LiteLLM (drop `--batch`),
  and reserve `--batch` for a direct-Anthropic key.
- **Structured outputs fail** → the proxy is an OpenAI-compatible gateway
  (`/chat/completions`), not an Anthropic passthrough. Switch to the
  OpenAI-compatible answering backend below — no code change needed.

#### OpenAI-compatible gateways (`--answering litellm:<alias>`)

If the gateway exposes only `/chat/completions` (the common enterprise LiteLLM
config), use the `litellm:<model-alias>` answering backend. It sends the SAME
scaffold, user prompt, and ProposedChange JSON schema as the native backend —
only the wire format differs (`response_format: json_schema`, which LiteLLM
translates per backend), so the held-constant contract (ADR-0001) is preserved.
Probe first, then run:

```bash
export LITELLM_BASE_URL=https://your-litellm      # the OpenAI-compatible root
export LITELLM_API_KEY=sk-litellm-virtual-key     # (fallbacks: OPENAI_BASE_URL / OPENAI_API_KEY)
python -m scripts.litellm_probe --mode openai --model <alias>   # exact adapter request
python -m runner.cli compare --answering litellm:<alias> --embedder local-hash \
  --arms no_grounding,rac_grounding --ns 10,50 --seeds 0-4
# or: ANSWERING=litellm:<alias> ./scripts/run_real.sh
```

Which mode is yours? Ask whoever runs the gateway, or just probe both — each
probe is a couple of tiny calls:

| Probe result | Run with |
| --- | --- |
| native mode passes | `--answering claude` + `ANTHROPIC_BASE_URL` (Batch OK if line 2 passed) |
| only openai mode passes | `--answering litellm:<alias>` (synchronous only) |
| neither passes | the gateway blocks schema-enforced JSON — scoring needs it; fix the gateway config |

Two limits on the OpenAI surface: **no Batch API** (`--batch` / `make
real-batch` refuse; they need a direct-Anthropic key), and **stdlib transport**
(no extra dependency — `pip install -e '.[real]'` isn't needed for a
litellm-only run).

Two caveats when proxied, regardless of mode:

- **Model identity.** With `--answering claude` each report records
  `answering_model.version` as `claude-opus-4-8` (a pinned constant) — make sure
  the proxy's alias maps to that exact model. With `litellm:<alias>` the report
  records the spec string itself, which is honest but only as meaningful as the
  alias: **pin the gateway alias to a fixed model** (not "latest"), or the
  recorded identity is misleading and the run isn't reproducible.
- **Cost numbers.** `scoring/cost.py` prices at Anthropic's published list rates.
  Token counts stay accurate if the proxy forwards `usage`, but the £/$ figures
  are list-price estimates — they won't reflect a proxy's markup or your
  organisation's contract.

### Real-corpus pilot (PEP supersession)

`scenarios_real/` holds the first **real, public-derived** corpus: the
**PEP 386 → PEP 440** version-scheme supersession. PEP 386 carries
`Status: Superseded` / `Superseded-By: 440`; PEP 440 (`Replaces: 386`) states
"this PEP MUST be used … and supersedes PEP 386 … Tools SHOULD ignore any
versions which cannot be parsed by the rules in this PEP." An agent that reaches
for PEP 386's retired `verlib`/`NormalizedVersion` scheme is following a
superseded decision; the adherent move is to cite PEP 440 instead. See
`rac/decisions/ADR-0002-real-corpus-pilot-peps.md`.

The PEPs are ingested as **RAC-native `decision` artifacts**: each carries the
verbatim PEP under a `## Source Text` section, wrapped in a decision envelope
(`Status`/`Context`/`Decision`/`Consequences`) plus a directional `## Supersedes`
edge — every envelope value derived from the PEP's own headers — so the `rac` arm
can classify them and follow the supersedes edge (see
`rac/decisions/ADR-0003-rac-arm-pep-integration.md`). The corpus is pinned to one
immutable commit of `python/peps` and fully reproducible — nothing in it is
hand-written PEP prose:

```bash
# Regenerate the corpus from the pin, or verify it reproduces byte-for-byte.
python -m ingest.peps build  --out scenarios_real/peps_version_supersession
python -m ingest.peps verify --out scenarios_real/peps_version_supersession
```

Run the pilot for real (needs `[real]` + both keys, exactly as above):

```bash
python -m runner.cli compare \
  --arms context_dump,naive_rag,no_grounding,rac \
  --answering claude --embedder voyage:voyage-4-large \
  --scenarios scenarios_real --seed 0
```

The `rac` arm is the grounding layer under test: it follows the typed
`supersedes` edge and supplies the live PEP 440, where `naive_rag` can surface
PEP 386's appealing `verlib` section without the header that marks it superseded.
It needs AsDecided Core's `decided` CLI on PATH (install `asdecided-core`, or
set `DECIDED_BIN`); drop `,rac` to run the baselines alone.

This produces the first genuine decision-adherence result (win, tie, or loss)
on a real corpus; like every run it is appended to `results/`. The build
environment for this pilot had no API keys, so the scenario is offline-validated
(loads, schema-validates, scores, and the `rac` arm's supersedes-following is
verified against the real AsDecided Core CLI) and the real numbers are produced by whoever
holds the keys.

### Real adherence-vs-N curve (real distractors, not synthetic filler)

The headline curve grows the corpus to N ∈ {10,50,150,300}. By default it pads
with synthetic `note` filler (illustrative). For a real curve, pad instead with
**real public PEP decisions** drawn from a pinned pool — a far harder, fairer
distractor set, since a typing-blind retriever can no longer dismiss them as
non-decisions (see `rac/decisions/ADR-0004-real-distractor-curve.md`):

```bash
# Build the pinned real PEP pool once (~644 PEP decisions; provenance.json is
# committed, the bulky corpus is rebuilt on demand and gitignored).
python -m ingest.peps pool build            # or: make pool
python -m ingest.peps pool verify           # re-checks it reproduces from the pin

# The real curve. Offline here is plumbing; the real result needs keys + Voyage.
python -m runner.cli demo \
  --scenarios scenarios_real \
  --arms context_dump,naive_rag,no_grounding,rac \
  --distractors real --ns 10,50,150,300 \
  --answering claude --embedder voyage:voyage-4-large   # make crossover-real ANSWERING=claude EMBEDDER=voyage:voyage-4-large
```

The pool is a *pin*, not a content dump: `provenance.json` records the exact PEP
set + per-PEP sha256 + the real `supersedes` edges among them, and `pool verify`
re-checks it byte-for-byte. **A robust curve needs more than one discriminating
scenario:** the pool exposes ~28 real supersedes edges, and additional scenarios
derived from them (each with a hand-authored, blind gold label) are the next
increment — see ADR-0004.

Tests:

```bash
pip install -e .[dev]   # or: pip install pytest
make test
```

## What's real vs. stubbed in this pass

| Component | State |
| --- | --- |
| Scenario + RunResult JSON Schemas (Draft 2020-12) | ✅ real |
| Provider adapter contract | ✅ real |
| `context_dump`, `naive_rag`, `no_grounding` arms | ✅ real, runnable offline |
| Deterministic scorer + metrics + crossover chart | ✅ real |
| Runner CLI (`run` / `compare` / `demo`), append-only reports | ✅ real |
| Five worked scenarios (incl. negative control + conflicting-scoped) | ✅ real, synthetic |
| Governing-decision recall diagnostic | ✅ real |
| Pinned Claude answering model (`--answering claude`, Opus 4.8) | ✅ implemented; needs `[real]` + `ANTHROPIC_API_KEY` |
| Real embeddings (`--embedder voyage:…` / `st:…`) | ✅ implemented; needs `[real]` / `[local-embeddings]` |
| `rac` arm (typed retrieval, follows `supersedes`) | ✅ verified against the `rac` CLI on the real corpus; needs `rac` on PATH |
| Real/public-derived scenario (PEP 386→440 supersession) | ✅ corpus built, pinned + verifiable; real run needs `[real]` + keys |
| Real distractor pools for the N-curve | ✅ PEP pool (`ingest.peps pool`, ~644) + RFC pool (`ingest.rfcs pool`, ~1125); curve runs well past N=300 on real distractors |
| Real discriminating scenarios — 9 PEP + 9 RFC + 1 W3C (superseded + prohibition) | ✅ deterministic, blind gold labels, offline-validated; several independently authored |
| Three real domains (PEP `Replaces`, RFC `Obsoletes`, W3C `Previous version` edges) | ✅ `ingest.peps` / `ingest.rfcs` / `ingest.w3c` (pinned; `verify` reproduces) |
| `memory_provider` arm | ⏳ typed stub + TODO |
| LLM-judge fallback | ⏳ disclosed, not built |

> **Pinned model caveat:** the answering model is `claude-opus-4-8`, which
> rejects `temperature`/`top_p`/`seed` (the API 400s on them). There is no
> temperature/seed knob to pin; the held-constant guarantee rests on the fixed
> model id + scaffold + structured JSON output, and run-to-run variance is
> reported as a metric. `temperature` is recorded as `null`.

## Repository layout

```
decisiongrounding/
  rac/         RAC knowledge corpus — decisions/ (ADRs), roadmaps/, designs/;
               the repo dogfoods the artifact format the benchmark studies
               (gated by rac validate / relationships --validate / review)
  spec/        FROZEN scenario taxonomy + scoring rubric (pre-registration)
  schema/      JSON Schema (Draft 2020-12) for Scenario and RunResult
  providers/   uniform adapter (prepare/respond) + the arms + answering/embedding
  scenarios/   loader + worked scenarios with tiny synthetic corpora
  scenarios_real/  real/public-derived corpora (PEP supersession pilot)
  ingest/      deterministic ingest of public artifacts (PEPs) into corpora
  scoring/     deterministic scorer, metrics, crossover dataset + chart
  runner/      CLI; pins model + seed; append-only report writer
  results/     append-only run outputs (generated; not committed)
  tests/       schema, scorer, ingest, real-corpus, and offline arm-smoke coverage
```

## Add an arm

1. Implement a `Provider` in `providers/` with `prepare(corpus)` and
   `respond(task) -> ProposedChange` (subclass `providers.base.Provider`; the
   shared `respond` already feeds the held-constant answering model — override it
   only if your grounding is task-dependent, as `naive_rag` does).
2. Register it in `providers/__init__.py` `ARMS` and, if it should run in the
   default demo, add it to `REAL_ARMS`.
3. Add it to the `arm` enum in `schema/run_result.schema.json`.
4. Run `make test` and `make compare ARMS=context_dump,naive_rag,your_arm`.

Your arm gets exactly one symmetric grounding opportunity and the same answering
model as every other arm. That is the whole point.
