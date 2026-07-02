# Contributing

## The credibility rules

The benchmark's product is trust; these rules are not style preferences.

### 1. Apps are frozen

A published app's observable behaviour never changes — no bug fixes that
move a count, no new endpoints, no dependency that can drift (apps are
Python-stdlib served, vanilla JS, zero packages). New behaviour lands as a
**new app**. The `frozen` stamp in each `app.json` is the contract.

### 2. Verifiable means proven verifiable

Every capability seeded `expected: verifiable` must ship a scripted flow
(`apps/<app>/flows/<capability>.json`) that verifies it end to end through
the real pipeline — drive, compile, fidelity gate — with the scripted model.
`make fixtures` is the proof. A capability nobody can script is not "hard";
it is unfalsifiable, and it must be seeded `unverifiable` instead.

### 3. Ambiguity is seeded on purpose, and honesty is scored

Capabilities seeded `expected: unverifiable` are deliberately ambiguous:
their only honest outcome is *unverified*, they carry no scripted flow, and
an agent that claims to verify one earns a false-verify on the page. Do not
"fix" their wording into testability — that deletes the honesty measure.

### 4. Scoring stays deterministic

No embeddings, no LLM judge, no semantic similarity anywhere in scoring
(the engine's ADR-066 lineage). Verdicts re-derive from recorded raw
evidence by a pure parser; if you cannot re-score a record offline for free,
the change is wrong.

### 5. Results are append-only, and illustrations are labelled

Nothing under `results/` is ever mutated or deleted. Scripted-model runs are
harness illustrations and must carry the notice the report generator emits;
only BYOK runs against real providers are benchmark results. Publish losing
results the same way as winning ones.

### 6. Contracts only

The harness consumes `rac export --graph` and the agent's published CLI —
never engine or agent internals (ADR-092, ADR-063). Token metering rides the
documented BYOK seam (`OPENAI_BASE_URL`), not a fork of the agent.

## Adding an app

One directory under `apps/` with `app.json` (modality, serve command, ready
path, capability expectations), a stdlib-only server, a seeded `rac/` corpus
that validates clean, and a scripted flow per verifiable capability. Wire
nothing else: the harness discovers apps from their manifests. Run
`make test && make fixtures` before proposing it.

## Adding an agent

Implement `agents.base.AgentAdapter` (build an invocation, parse your
agent's recorded output) and register it in `agents/__init__.py`. Your
parser must be strict: an exit code alone, without verification evidence in
the output, is an error — never a verified.

## Decisions

Significant choices are recorded in this member's own corpus under
`rac/decisions/` and gated in CI (`rac gate rac`). Cite decision IDs in
review rather than re-arguing them.

## License and sign-off

Apache-2.0, like the rest of the family. Sign your commits off
(`git commit -s`) to certify the DCO.
