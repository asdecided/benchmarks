# AsDecided Benchmarks

[Product site](https://asdecided.com/) · [Ecosystem documentation](https://asdecided.com/docs/ecosystem/) · [Canonical sources](https://asdecided.com/sources)

Evaluation suites for [AsDecided](https://github.com/asdecided/core)
(requirements-as-code) — one subdir per benchmark. Per ADR-092 (one repo per
concern, subdir per member) this is the single home for RAC's benchmarks; future
suites land as sibling subdirs rather than new repositories.

Each benchmark consumes the engine only as an **external CLI on `PATH`** and imports
no engine code (DG-ADR-0001), so the suites stay decoupled from the engine's
internals. Scoring is deterministic and offline — no embeddings, no LLM judge,
no network, no randomness, no clock in the scored path (ADR-066): the
serialized `metrics` block is byte-identical across runs on an unchanged
corpus.

## Members

| Subdir | Benchmark |
| --- | --- |
| [`autonomousqa/`](autonomousqa/) | Autonomous-QA benchmark — frozen sample apps across four drive modalities with seeded corpora; agent-agnostic, deterministic evidence-based scoring (ADR-066), Proofkeeper as the reference agent over its published CLI. |
| [`decisiongrounding/`](decisiongrounding/) | Decision-grounding eval — does an agent connected to RAC respect recorded decisions? Deterministic scoring, no embeddings / no LLM judge (ADR-066). |
| [`search-artifacts/`](search-artifacts/) | Ranked retrieval quality of the `search_artifacts` MCP tool: P@k / R@k / MRR over a 39-artifact, five-type corpus; full-list hard negatives and an adversarial graph-boost gate cluster. |
| [`find-decisions/`](find-decisions/) | The live-decision query's supersession defense: retired decisions must never surface, even as the lexically best match. |
| [`get-artifact/`](get-artifact/) | Exact-id resolution contract: alias and case-insensitive hits, duplicate and not-found error shapes. Conformance gated at 1.0. |
| [`get-related/`](get-related/) | Relationship-edge retrieval: exact incoming AND outgoing edge sets per artifact. Conformance gated at 1.0. |
| [`get-summary/`](get-summary/) | Portfolio summary contract: counts by type, empty-corpus shape, byte stability. Conformance gated at 1.0. |
| [`sentry/`](sentry/) | Deterministic decision-to-code enforcement: 80 contract cases plus generated 5,000-decision scale evidence for recall, clean-pass behaviour, attribution, diff isolation, SARIF, gate parity, and byte determinism. |
| [`gitchameleon/`](gitchameleon/) | External evidence run (scaffold): does grounding in recorded version-pin decisions improve version-correct codegen on GitChameleon 2.0? Upstream executable-test scoring; never a merge gate. |

## Shared harness

[`harness/`](harness/) is the shared package the per-tool benchmarks consume:
a subprocess runner (the engine as an external CLI), a deterministic scorer, a
`{metrics, metadata, per_query}` scorecard writer, and a CI gate. Each
benchmark subdir is a thin `run.py` over it, with the `rac eval` flag surface:

```
python3 <benchmark>/run.py                     # human summary
python3 <benchmark>/run.py --json              # full scorecard
python3 <benchmark>/run.py --check             # gate: exit 0 / 1 / 2
python3 <benchmark>/run.py --update-baseline   # human-gated; CI never runs this
```

Gate semantics (per benchmark `config.json`): `negative_violations == 0`
always; gated metrics must meet their floors and stay within tolerance of the
committed `baseline.json`. Baselines change only through a human-reviewed
`--update-baseline` commit.

## Running the battery

```
brew install asdecided/tap/asdecided-core
export RAC_BIN=decided   # temporary benchmark adapter variable
pip install -e ".[dev]"
python -m pytest -q
```

## History

`decisiongrounding/` is the former **`itsthelore/decisiongrounding`** repository,
moved here with its history preserved (ADR-092 convergence). Its deterministic
scoring contract (ADR-066) is untouched. The benchmark currently names its
grounding arm and adapter variable `rac`/`RAC_BIN`; point that adapter at the
native `decided` executable as shown above. Renaming the benchmark vocabulary
is separate from this repository-topology cutover.

## License

Apache-2.0 (see `LICENSE` and `NOTICE`). Contributions require DCO sign-off
(`git commit -s`).
