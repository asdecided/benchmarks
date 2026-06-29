# rac-benchmarks

Evaluation suites for [RAC](https://github.com/itsthelore/rac-core)
(requirements-as-code) — one subdir per benchmark. Per ADR-092 (one repo per
concern, subdir per member) this is the single home for RAC's benchmarks; future
suites land as sibling subdirs rather than new repositories.

Each benchmark consumes `rac` only as an **external CLI on `PATH`** and imports
no engine code, so the suites stay decoupled from the engine's internals.

## Members

| Subdir | Benchmark |
| --- | --- |
| [`decisiongrounding/`](decisiongrounding/) | Decision-grounding eval — does an agent connected to RAC respect recorded decisions? Deterministic scoring, no embeddings / no LLM judge (ADR-066). |

## History

`decisiongrounding/` is the former **`itsthelore/decisiongrounding`** repository,
moved here with its history preserved (ADR-092 convergence). The benchmark runs
unchanged against the published `rac` CLI; its deterministic scoring contract
(ADR-066) is untouched.
