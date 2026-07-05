# scale — single-node scale evidence run (scaffold)

A deterministic **corpus generator** and a **latency/memory harness** for
measuring how the `rac` engine behaves as a corpus grows — from a thousand
artifacts to a million — on a single node. It answers one question in
evidence terms: *does warm retrieval stay flat, and is incremental work
bound by the changeset rather than the corpus size?*

Like [`gitchameleon/`](../gitchameleon/), this is an **evidence run, never a
merge gate** (ADR-066 / ADR-097). It consumes `rac` strictly as an external
CLI and MCP server on `PATH` — no engine imports (DG-ADR-0001) — and depends
on nothing but the Python standard library.

## Pieces

| File | Role |
| --- | --- |
| `generate_corpus.py` | Deterministic generator: N valid RAC artifacts in a realistic type mix, sharded, byte-identical for a given `(count, seed)`. |
| `measure.py` | Harness: CLI one-shot wall-clock + RSS, warm MCP retrieval percentiles, and an incremental changeset probe; writes a re-plottable results JSON. |
| `gate.py` | Rerunnable performance gate: asserts the SCALE_TARGET budgets against one or more results files (multiple sizes ⇒ flatness check). |
| `_common.py` | Engine-free shared helpers: deterministic id encoding, type layout, and the query vocabulary both sides draw from. |

## Generate a corpus

```
python scale/generate_corpus.py --count 100000 --out /tmp/scale-100k --seed 42 --manifest
```

- Emits ~55% requirement / 25% decision / 10% roadmap / 5% prompt / 5%
  design. Every artifact classifies as, and passes `rac validate` for, its
  type; ~60% of requirements carry a `## Related Decisions` section citing 1-3
  real decision ids, and decisions form supersession chains, so
  `rac relationships --validate` passes.
- **Deterministic**: content is a pure function of `(seed, index)` — no clock,
  no filesystem-order dependence. The same `(count, seed)` produces a
  byte-identical tree (`diff -r` is empty).
- **Sharded**: `<out>/shard-000/…` with ≤2000 files per shard directory.
- `--manifest` writes `manifest.json` (count, seed, per-type counts, and a
  sha256 over the sorted `(relpath, size)` list) for reproducibility checks.
- Ids are `RAC-SCA<9-char Crockford base32>` — a valid engine id derived
  from the artifact index (the spec's `RAC-SCALE-<n>` sketch is not a legal
  engine id; this is the conforming equivalent).

## Measure

```
python scale/measure.py --corpus /tmp/scale-100k --out results-100k-cache.json \
    --queries 50 --runs 3 [--mcp-cache | --mcp-index]
```

- **CLI one-shot** (median of `--runs`, default 3), with child peak RSS:
  `validate`, `find`, `resolve`, `relationships --validate`,
  `export --documents` (to `/dev/null`). `--timeout S` (default 1800) records
  `{"timeout": true, "limit_s": …}` instead of failing.
- **Warm retrieval**: spawns `rac mcp --root <corpus> [--cache]`, speaks MCP
  JSON-RPC 2.0 over stdio (initialize handshake, then `tools/call`), issues a
  warm-up then `--queries` timed calls per tool, and records p50/p95/p99 ms
  for `search_artifacts` / `get_artifact` / `get_related` plus the server's
  peak RSS (`/proc/<pid>/status` `VmHWM`). `--mcp-cache` selects the `--cache`
  path and records `mode: "cache"`; `--mcp-index` selects the persistent-index
  path (`--index`, ADR-100/101) and records `mode: "index"` (the two are
  mutually exclusive); run once without and once with to compare.
- **Warm query classes**: each warm tool is measured under its *natural* query
  classes and the per-class percentiles are reported additively under
  `warm_retrieval.tools.<tool>.classes` (the top-level per-tool block is
  unchanged — it stays the tool's historical primary class). `search_artifacts`
  runs `broad` and `selective`; `get_artifact` and `get_related` run `lookup`. A
  **broad** query is one common vocabulary term: it matches a fixed ~10% of the
  corpus at every size, so its latency is dominated by serialising a
  thousands-of-matches payload rather than by the index — it is reported for
  continuity but is mode-independent and payload-serialisation-bound, so it is
  **not** the flat-latency signal the gate should read. A **selective** query is
  a three-term AND across the topic/subsystem/adjective pools whose terms rarely
  co-occur, so it prunes to a small handful of candidates and measures the query
  path (candidate generation + scoring), not payload serialisation — the
  representative warm-search class. A **lookup** query is an exact artifact id,
  the natural argument for the id-keyed tools (resolution and per-node edge /
  neighbourhood shaping). All classes are derived deterministically from the
  frozen `_common` vocabulary, so the harness reproduces them with no corpus read.
- **Incremental**: appends a harmless line to ~1k files, then re-runs
  `validate` and one warm search — separating changeset-bound from
  corpus-bound cost.
- Every long child runs in its own session; a timeout kills the whole process
  group, so a hung 1M run cannot wedge the box.

Results JSON carries `{schema_version, corpus{count,path,manifest_sha}, node,
engine{version}, mode, measurements{…}}` — everything needed to re-plot.

## SCALE_TARGET budgets

The budgets `gate.py` enforces (the gate is the executable copy of this
table), sized for the ~15 GB single-node reference:

| Budget | Target |
| --- | --- |
| Warm retrieval p50 (per tool) | < 30 ms, flat across the curve |
| Warm retrieval p99 (per tool) | < 100 ms, flat across the curve |
| Incremental re-validate | < 5 s, corpus-size-independent |
| Cold build (`rac validate`) | ≤ ~2 min per 1M artifacts |
| Working set (peak RSS) | ≤ ~10 GB on the 15 GB reference node |
| Flatness | largest size within 1.5x of smallest |

## Gate

```
python scale/gate.py results-1k-cache.json results-100k-cache.json results-1m-cache.json
```

One file checks the absolute budgets; several (one per size) add the flatness
check — warm p50/p99 and incremental time at the largest size must stay within
1.5x of the smallest. Exit 0 when every budget holds, 1 otherwise. A failing
budget is honest evidence about the measured build, not a broken gate.

## Reproduce the scaffold's own smoke run

```
python scale/generate_corpus.py --count 1000 --out /tmp/scale-1k --seed 42 --manifest
rac validate /tmp/scale-1k
rac relationships /tmp/scale-1k --validate
python scale/measure.py --corpus /tmp/scale-1k --out /tmp/r-nocache.json --queries 10 --runs 1
python scale/measure.py --corpus /tmp/scale-1k --out /tmp/r-cache.json  --queries 10 --runs 1 --mcp-cache
python scale/gate.py /tmp/r-nocache.json /tmp/r-cache.json
```

`rac` must be on `PATH` (external CLI only — no engine imports, DG-ADR-0001).
