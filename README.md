# rac-benchmarks

Evaluation suites for [RAC](https://github.com/itsthelore/rac-core)
(requirements-as-code) — one subdir per benchmark. Per ADR-092 (one repo per
concern, subdir per member) this is the single home for RAC's benchmarks; future
suites land as sibling subdirs rather than new repositories.

Each benchmark consumes `rac` only as an **external CLI on `PATH`** and imports
no engine code (DG-ADR-0001), so the suites stay decoupled from the engine's
internals. Scoring is deterministic and offline — no embeddings, no LLM judge,
no network, no randomness, no clock in the scored path (ADR-066): the
serialized `metrics` block is byte-identical across runs on an unchanged
corpus.

## Members

| Subdir | Benchmark |
| --- | --- |
| [`decisiongrounding/`](decisiongrounding/) | Decision-grounding eval — does an agent connected to RAC respect recorded decisions? Deterministic scoring, no embeddings / no LLM judge (ADR-066). |
| [`search-artifacts/`](search-artifacts/) | Ranked retrieval quality of the `search_artifacts` MCP tool: P@k / R@k / MRR over a 30-artifact, five-type corpus; full-list hard negatives. |
| [`find-decisions/`](find-decisions/) | The live-decision query's supersession defense: retired decisions must never surface, even as the lexically best match. |
| [`get-artifact/`](get-artifact/) | Exact-id resolution contract: alias and case-insensitive hits, duplicate and not-found error shapes. Conformance gated at 1.0. |
| [`get-related/`](get-related/) | Relationship-edge retrieval: exact incoming AND outgoing edge sets per artifact. Conformance gated at 1.0. |
| [`get-summary/`](get-summary/) | Portfolio summary contract: counts by type, empty-corpus shape, byte stability. Conformance gated at 1.0. |

## Shared harness

[`harness/`](harness/) is the shared package the per-tool benchmarks consume:
a subprocess runner (rac as an external CLI), a deterministic scorer, a
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
pip install "git+https://github.com/itsthelore/rac-core.git"   # rac on PATH
pip install -e ".[dev]"
python -m pytest -q
```

## History

`decisiongrounding/` is the former **`itsthelore/decisiongrounding`** repository,
moved here with its history preserved (ADR-092 convergence). The benchmark runs
unchanged against the published `rac` CLI; its deterministic scoring contract
(ADR-066) is untouched. Its port onto the shared harness is tracked as a
`tool-benchmarks` roadmap initiative in rac-core and deliberately does not
expand the frozen restructure item's scope.

## License

Apache-2.0 (see `LICENSE` and `NOTICE`). Contributions require DCO sign-off
(`git commit -s`).
