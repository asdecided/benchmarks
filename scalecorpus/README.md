# scalecorpus — single-node scale benchmark for the RAC engine

Measures whether the engine's operational paths are **scale-invariant** on a
single node: warm retrieval latency, incremental re-validation cost, cold
full-build time, and resident memory, across a corpus-size curve. Sibling to
the other members (ADR-092): drives `rac` strictly as an external process on
`PATH` (DG-ADR-0001 — zero engine imports), deterministic inputs, JSON
scorecards.

## Pieces

- `generate.py` — deterministic corpus generator. A corpus is a pure function
  of `(size, seed)`: identical bytes on any machine with any worker count.
  Artifacts cover all five types, validate cleanly (`rac validate` exit 0,
  `rac relationships --validate` exit 0), and carry a stratified vocabulary
  (COMMON ≈ 33% of docs, MID ≈ 2%, RARE ≈ 0.05%) so retrieval terms have known
  selectivity. Files shard 1,000 per directory.

  ```
  python3 scalecorpus/generate.py --size 1000000 --out /path/with/room/c1m
  ```

  Corpora are generated OUTSIDE any git tree (millions of files make git
  unusable) and deleted after their measurements land. Budget ~4 GB of disk
  per million artifacts.

- `perf.py` — the measurement harness. Emits a JSON scorecard per
  `(engine, corpus size, cache mode)` run:
  - **warm retrieval** — long-lived `rac mcp` stdio session; per-call
    p50/p95/p99 across a deterministic mixed workload (point lookup, graph
    neighbourhood, selective and broad search). `--cache` toggles ADR-099.
  - **cold CLI** — one-shot `rac resolve` / `rac find` wall time.
  - **cold full validate** — `rac validate <corpus>`: wall time + peak RSS.
  - **incremental validate** — re-validate after a deterministic
    ~1,000-artifact changeset (applied, measured, restored).
  A run that exceeds the timeout is recorded as **DNF** — failing to finish
  at scale is a result, not an error.

  ```
  python3 scalecorpus/perf.py --corpus /path/c1m --size 1000000 \
      --out scalecorpus/results/before-1m.json --cache
  ```

- `results/` — committed scorecards. `before-*` = legacy engine baselines.

## Scale target (the gate, per roadmap `rebuild-scale`)

Measured on the stated reference node, at every corpus size on the curve:

| Budget | Target | Shape requirement |
| --- | --- | --- |
| warm retrieval | p99 < 100 ms, p50 < 30 ms | FLAT across the curve |
| incremental validate (~1k changeset) | < 5 s | corpus-size-independent |
| cold full build | ≤ ~2 min per 1M artifacts | linear, parallel |
| working set | ≤ ~2/3 node RAM | index on disk (mmap) |

The claim is scale-invariance — a flat line across the curve — not one lucky
point. A wall is reported with numbers, never narrowed or faked.
