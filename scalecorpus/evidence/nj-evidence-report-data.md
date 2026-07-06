# nj — evidence report data appendix (rerunnable)

Every headline number in the nj-* Evidence Desk deliverables, with the exact
scorecard path and command that reproduces it. All figures are read from
`scalecorpus/results/`. Reference node: 4 vCPU / 15 GiB / no swap, seed 7.
`rac` is driven strictly as an external process on PATH (zero engine imports).

## How the scorecards are produced

```
# deterministic corpus (pure function of size, seed; generated outside any git tree)
python3 scalecorpus/generate.py --size <N> --seed 7 --out /path/cN

# one scorecard per (engine, size, cache mode)
python3 scalecorpus/perf.py --corpus /path/cN --size <N> \
    --out scalecorpus/results/<before|after>-<tag>.json [--cache]

# apply the scale gate to a scorecard set
python3 scalecorpus/run.py --check --results scalecorpus/results --pattern 'after-*.json'
```

`before-*` = legacy engine baseline; `after-*` = rebuilt engine. `-cache`
scorecards carry the warm-serving (`rac mcp`) evidence; plain scorecards carry
cold CLI, full validate, and incremental validate. `*-validate-{cold,incr}.timing`
sidecar files carry the ADR-103 detect/recompute split.

---

## 1. Warm serving latency (the lead curve)

Field: `metrics.warm_retrieval.per_tool.<tool>.p50_ms` (per-tool);
`metrics.warm_retrieval.p50_ms` (blended).

| Size | Legacy blended p50 | Legacy get_artifact | Rebuilt get_artifact | Rebuilt get_related | Source (legacy / rebuilt) |
|---|---|---|---|---|---|
| 1k | 185.52 ms | 96.36 ms | 10.44 ms | 6.92 ms | `before-1k-cache.json` / `after-1k-cache.json` |
| 10k | 2,178.76 ms | 1,136.25 ms | 16.03 ms | 21.27 ms | `before-10k-cache.json` / `after-10k-cache.json` |
| 100k | 16,466.43 ms | 15,419.24 ms | 9.82 ms | 32.12 ms | `before-100k-cache.json` / `after-100k-cache.json` |
| 1M | crash (OOM) | crash | crash (index build OOM) | crash | `before-1m-cache.json` / `after-1m-cache.json` |

- **1,573x point-lookup cut @100k** = 15,419.24 / 9.82 (`before-100k-cache.json`
  vs `after-100k-cache.json`, `per_tool.get_artifact.p50_ms`).
- **get_related @100k = 32.12 ms, 2 ms over the 30 ms p50 budget** (`WARM_P50_MS`
  in `run.py`). Source `after-100k-cache.json`.
- **1M crash**: both cards record `warm_retrieval.crashed=true`,
  `error="ExceptionGroup: unhandled errors in a TaskGroup (1 sub-exception)"`.
  The rebuilt crash is on index BUILD (peak ~15.9 GiB on the 15 GiB node);
  serving would fit.
- No-cache legacy warm p50 (for the stat-grid "from 79 s"): 1,166.07 / 11,734.35 /
  102,940.12 ms at 1k/10k/100k blended; `after-*.json` (`cache=false`) and
  `before-*.json`. The task-summary "896 / 9,679 / 79,394 ms" is the legacy
  no-cache point-lookup line.

Reproduce: `perf.py --corpus /path/cN --size N --out ...-cache.json --cache`.

## 2. Search (Theta of match count)

Field: `per_tool.search_artifacts[rare|mid].p50_ms`.

| Size | Rebuilt rare p50 | Broad p50 | Source |
|---|---|---|---|
| 1k | 10.19 ms | 69.87 ms (mid) | `after-1k-cache.json` |
| 10k | 24.37 ms | 4,060.77 ms (mid) | `after-10k-cache.json` |
| 100k | 654.95 ms | 412,379.29 ms over ~27k matches | `after-100k-cache.json` / `after-100k-broad.json` |
| 1M | — | DNF, warm-up call exceeded 1,200 s | `after-1m-broad.json` |

- **~1.6 ms per matching doc** invariant: rare-term p50 grows 10 to 655 ms as the
  match set grows ~4 to ~400 across 1k to 100k.
- **412 s broad call**: `after-100k-broad.json`,
  `per_tool.search_artifacts[mid].p50_ms = 412379.29`. Reported, never gated
  (`run.py` `check()` narrows the size-invariance gate to `get_artifact` /
  `get_related`; both search classes are printed report-only).

## 3. Validate — full, cold build, incremental

Full/incremental wall: `metrics.full_validate.wall_s`,
`metrics.incremental_validate.wall_s`. Detect/recompute split:
`*-validate-{cold,incr}.timing` (`detect_ms`, `recompute_ms`, `files_changed`).

| Size | Legacy full validate | Rebuilt cold build (detect+recompute) | Rebuilt incremental, 1k changeset | Cold budget |
|---|---|---|---|---|
| 1k | 0.96 s | 1.00 s (0.036 + 0.962) | 1.01 s (0.037 + 0.975) | — |
| 10k | 8.32 s | 9.98 s (0.363 + 9.621) | 1.16 s (0.233 + 0.927) | — |
| 100k | ~77 s | 99.31 s (3.986 + 95.324) | **3.92 s** (2.613 + 1.310) | 12 s |
| 1M | 1,163.84 s (6.32 GB RSS) | 686.43 s (93.319 + 593.108) | 20.94 s (17.909 + 3.027) | 120 s |

Sources: rebuilt `after-{1k,10k,100k,1m}-validate-cold.timing` and
`-validate-incr.timing`; legacy 1M `before-1m-validate.json`
(`full_validate.wall_s=1163.84`, `peak_rss_mb=6319.1`), `before-1m-incr.json`
(`incremental_validate.wall_s=1017.5`).

- **Legacy incremental == full at every size** (no incremental path): legacy
  `incremental_validate.wall_s` equals `full_validate.wall_s` in every
  `before-*.json`.
- **Incremental gate (`INCR_S = 5.0` s, `run.py`)**: pass at 100k (3.92 s),
  fail at 1M (20.94 s). The 1M failure is detection (17.909 s), not recompute
  (3.027 s, flat).
- **Cold-build budget (`COLD_S_PER_1M = 120` s, pro-rated)**: 686 s @1M vs 120 s
  = **5.7x over**; 99.31 s @100k vs 12 s = 8.2x over.

Reproduce timing sidecars: run `rac validate --cache` under the curve driver,
which emits `rac-timing: detect_ms=... recompute_ms=... files_changed=...`.

## 4. Working set (server RSS)

Field: `metrics.warm_retrieval.server_peak_rss_mb`.

| Size | Legacy cache-server peak | Rebuilt server peak | Source |
|---|---|---|---|
| 1k | 87.3 MB | 87.1 MB | `before-1k-cache.json` / `after-1k-cache.json` |
| 10k | 297.7 MB | 320.0 MB | `before-10k-cache.json` / `after-10k-cache.json` |
| 100k | 1,931.0 MB | 2,668.9 MB | `before-100k-cache.json` / `after-100k-cache.json` |
| 1M | crash | index build OOM ~15.9 GiB | `before-1m-cache.json` / `after-1m-cache.json` |

- **~22 MB per 1,000 artifacts** legacy growth: 1,931.0 MB / ~100k ≈ 19-22 MB/1k;
  the resident working set would exhaust the node in the low millions.
- Memory ceiling `MEM_CEILING_MB = 10 * 1024` (≈2/3 of the 15 GiB node) in `run.py`.

## 5. Deterministic work counts (Movement A, byte-identical)

Field: `runs[].counts.<hook>` in `workcounts-{before,after}.json` (corpus c1k),
captured via `sys.setprofile` by code-object identity.

| Path (c1k) | Hook | Legacy | Rebuilt |
|---|---|---|---|
| `validate` | classify | 3,000 | 1,000 |
| `validate` | parse_file | 1,000 | 1,000 (unchanged) |
| `index` / `find` / `resolve` / `relationships` | classify | 1,000 | 1,000 |

- **classify 3x to 1x on validate**: `workcounts-before.json` run[0].counts.classify=3000
  to `workcounts-after.json` run[0].counts.classify=1000. `stdout_bytes` identical
  (102) — byte-parity preserved.
- **parse_file unchanged** (honest): 1,000 to 1,000. The win is removing redundant
  classification, not re-reading.
- **"corpus to 1 row" serving**: the point-lookup work reduction is the warm-latency
  story (section 1), not a workcounts row — legacy re-parses the whole corpus per
  serving call; rebuilt reads one indexed row.

## 6. Source metrics

Field: `src-{before,after}.json` (loc, docstrings, radon).

| Metric | Legacy | Rebuilt |
|---|---|---|
| Total lines | 27,309 | 30,583 (+12.0%) |
| Code lines | 21,599 | 24,023 |
| Files | 107 | 113 |
| Functions fully annotated | 1,119 / 1,138 (98.3%) | 1,324 / 1,324 (100%) |
| Duplicate blocks | 0 | 0 |
| Cyclomatic mean / max | 3.31 / 42 | 3.18 / 42 |
| CC blocks over 10 | 54 | 55 |

- **LOC +12%**: 27,309 to 30,583 (`total_lines`). New index/serving/incremental code.
- **100% annotated**: `functions_fully_annotated == functions` in `src-after.json`.
- Named CC hotspots refactored 39/31/24 to 12/3/10 (per-function; aggregate
  `cc_max` unchanged at 42, `cc_blocks_over_10` 54 to 55 — reported flat).

## 7. Behavior parity & fleet ledger (not in scorecards)

- **2,127 tests green** = 1,906 original untouched + human-approved Phase-0.5
  additions; 23-command byte-parity legacy-vs-rebuilt; corpus gates
  (`rac validate rac/`, `rac relationships rac/ --validate`) exit 0.
- **Parallel parse**: 1,043 to 1,873 files/s (1.79x on 4 cores).
- **Decisions on the record**: ADR-100 (unified derived read-model), ADR-101
  (persistent mmap index store), ADR-102 (event-sourced serving freshness),
  ADR-103 (incremental validation), ADR-104 (parallel cold build).
- **Fleet**: 41 Opus agents, ~6.9M subagent tokens, 30 commits.

---

## Figure to source map (nj-* deliverables)

| Figure / card | Primary sources |
|---|---|
| nj-fig-scale (lead curve) | `before-*-cache.json`, `after-*-cache.json` |
| nj-fig-stats (hero grid) | `after-100k*.json`, `after-1m-validate-cold.timing`, budgets in `run.py` |
| nj-fig-work (dumbbells) | `workcounts-before.json`, `workcounts-after.json` |
| nj-fig-misses (ledger) | `after-1m-*.json`, `after-1m-broad.json`, `src-after.json` |
| nj-fig-incr (detect vs recompute) | `after-100k-validate-incr.timing`, `after-1m-validate-incr.timing` |
| nj-banner | point-lookup @100k (section 1), test/parity ledger (section 7) |
| nj-report | all sections above |
