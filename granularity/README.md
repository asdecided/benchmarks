# granularity — retrieval impact of artifact granularity (evidence run)

Measures what ADR-010 (*Documents Are Not Artifacts*) asserts qualitatively:
the same knowledge, rendered two ways, retrieved and scored identically — with
the ranker held constant so **granularity**, not the ranker, is the variable.

Four arms over **one deterministic source of truth** (`_model.py`), so a
`(count, seed)` pair fixes every byte of both renderings and the query set.
Reruns on an unchanged corpus are byte-identical (ADR-066); this member is an
**evidence run, never a merge gate** (ADR-066 / ADR-097).

## The four arms

Three of the four share **one ranker** (the streaming Okapi BM25 in `bm25.py`);
only the chunk source differs, so a delta between them is a granularity or
liveness effect, never a ranker A/B.

- **artifacts** (engine) — one valid RAC artifact per file, served warm from
  `rac mcp --root artifacts/ --index` (ADR-100/101). Topic cases go to
  `search_artifacts`; supersession / related cases go to `find_decisions`, the
  typed live-decision tool whose filter the per-file `Superseded` status
  enables. This is the real typed engine: BM25F field weights, graph signal,
  prefix matching, RRF, and the liveness filter.
- **bm25-artifacts** — the *same per-file decision artifacts*, ranked by the
  member's own flat Okapi BM25 instead of the engine. Same ranker and same
  decision content as `canon`; the only difference is granularity (one file per
  artifact vs one `##` block per artifact).
- **canon** — the *same content* concatenated into one monolithic
  `decisions-canon.md`, one `##` heading block per artifact, ranked by the flat
  BM25 with **no liveness logic** (a document carries no typed identity for a
  live filter to read).
- **canon-status** — the canon arm plus one deterministic step: any block whose
  rendered `### Status` reads `Superseded` is dropped before ranking. The canon
  already carries that status line verbatim, so this is the strongest *honest*
  treatment a monolithic document supports.

### The three paired comparisons

`run.py` prints all four arms, then these three pairs per class, both
directions:

- **bm25-artifacts vs canon → pure granularity.** Identical ranker, identical
  decision content; only the file-vs-block split differs. In this corpus the two
  are **numerically identical** (every delta `0`): a flat lexical ranker gains
  nothing from splitting a document into files. This is the headline correction
  to the naive reading of ADR-010 — granularity alone is not the lever for
  lexical retrieval.
- **canon-status vs canon → what a status-aware parser recovers.** Reading the
  already-rendered status line drops every superseded block, taking
  supersession violations to **zero** and lifting P@1 / MRR on the
  supersession-defended classes — with no typed identity at all.
- **artifacts (engine) vs bm25-artifacts → what the typed engine adds beyond
  granularity.** The engine's win over the flat per-file ranker is the liveness
  filter (it matches `canon-status`), *not* the file split. On the plain
  `topic` class the engine and the flat ranker are level.

So the benefit ADR-010 points at is delivered by the **typed liveness filter**
(the engine, or the honest status-parser), reified by the per-file `Superseded`
status — and it is separable from mere granularity, which the shared-ranker pair
shows contributes nothing on its own here.

### bm25-artifacts domain and tie-break note

`bm25-artifacts` ranks **decision files only** — the same content domain as
`decisions-canon.md` — so its comparison against `canon` isolates granularity
alone. It streams files in sorted relative-path order; the zero-padded
`dec-<index>.md` names sort into the same index order the canon streams, so the
tie-break domains coincide here. The *residual* difference is that path sort
(not stream position) fixes ties, and the per-file chunk text carries the
artifact's frontmatter tokens (a small constant, uniform across all decision
chunks) that the canon block does not. The engine `artifacts` arm's `topic`
cases search the whole corpus via `search_artifacts`, a superset of the
decisions-only domain the two flat arms rank — an asymmetry inherited from the
member's original two-arm design and noted here for honesty.

## Scale-aware vocabulary (model_version 2)

The v1 corpus drew every query term from a fixed 40-topic pool, so at 100k
thousands of artifacts shared any term and all metrics collapsed into tie-break
noise. v2 adds a **coined per-chain pseudo-word** (`veltrik`, `tipikib`, …) — a
pure function of `seed:key`, woven into the title and prose. Chain members share
their coined term (so a named supersession query still collides the superseded
ancestor with its live head), but naming a family selects it out of the whole
corpus at any size. The coined word tokenises to one lowercase token, so it
never breaks classification or validation.

Queries split evenly, per class, into two selectivity forms:

- **named** — coined family name + one topic term. Its selectivity is
  size-independent (P@1 for the artifacts arm holds at 1.0 from 1k to 10k).
- **topical** — the v1 three-topic form, kept as the honest saturation
  baseline (its P@1 falls as the corpus grows).

`run.py` reports metrics per selectivity so the size-independent series is
separable from the saturating one. Corpora are **not comparable across model
versions**; the manifest and scorecard both record `model_version`.

## Multi-seed variance

A single seed gives no variance estimate. `run.py --seeds 42,43,44 --count N`
builds a corpus + query set per seed into a temp dir, runs the four arms on
each, and aggregates per metric per arm: **mean, min–max spread**, and — for
every pairwise delta — whether its **sign is consistent** across seeds. The
headline deltas (P@1, R@1, MRR, supersession violations for the two meaningful
pairs) are seed-stable; near-floor metrics (P@3 / R@3) can flag `mixed` when a
delta is a fraction of a percent, which the sign-consistency column surfaces
rather than hides. Default single-seed behaviour is unchanged and byte-identical
on rerun (ADR-066); multi-seed is an explicit opt-in.

## Why the canon arm is chunk-retrieval by construction

The engine physically cannot represent a canon file as many artifacts, so the
canon arm is framed honestly as what a team actually does with a monolithic
document — chunk it by heading and search the chunks lexically:

- **1 MiB file cap** — a canon of thousands of decisions blows past it.
- **One id per file** — a file carries a single frontmatter identity; a canon
  has no per-decision typed id for `resolve` / `find_decisions` to key on.
- **Duplicate-section collapse** — a file has one `## Status`, one `##
  Decision`; a canon repeating them per block is not a valid artifact.

So the canon arms chunk `decisions-canon.md` by its own `##` headings — the
strongest simple treatment such a document supports (no strawman chunker) — and
rank the chunks with a **streaming BM25** (`bm25.py`). Its tokenisation is
plainly documented: lowercase, then split on any non-alphanumeric boundary
(`[a-z0-9]+`), the same token-boundary rule the engine's search matches on
(ADR-037). Both families therefore rank on the same lexical family.

## Query classes (`queries.json`, ADR-097 family shape)

`{"id", "class", "selectivity", "query", "must_return": [live id],
"must_not_return": [superseded ancestor ids...]}`

- `topic` — a standalone live decision by its own terms; no negatives. A plain
  retrieval-quality comparison (a monolithic arm can win it; the scorecard
  reports that honestly).
- `supersession` — the heart: chain terms that collide the live head with its
  superseded ancestors (the hard negatives).
- `related` — a live chain head reached through a requirement that references
  it; a second, independently seeded population of the supersession-defense
  case.

## Scoring

Reuses the family scorer (`harness.scoring.score_retrieval_case`): P@1/3/5,
R@1/3/5, MRR (macro-averaged), and **supersession violations** — a
`must_not_return` id **anywhere** in the returned list (the full-list window,
not top-k: a superseded decision reaches an agent wherever it ranks). The
scorecard reports every metric for all four arms with signed deltas, in both
directions honestly.

## Run the ladder

```
export PATH=/path/to/rac/venv/bin:$PATH        # rac (with `mcp --index`) on PATH

python granularity/build_corpus.py  --count 1000 --out DIR --seed 42 --manifest
python granularity/build_queries.py --count 1000 --out DIR --seed 42
python granularity/run.py --corpus DIR          # writes DIR/results.json + tables

# multi-seed variance (opt-in; builds a temp corpus per seed):
python granularity/run.py --seeds 42,43,44 --count 1000 --out variance.json
```

The `--count` ladder is 1k / 10k / 100k, aligned with the scale member, for a
quality-versus-size curve per arm. `build_corpus.py` self-checks the per-file
variant with `rac validate` and `rac relationships --validate`. Both the builder
and every arm stream (one artifact / one chunk in memory at a time), so nothing
holds a whole canon — the 100k rung does not blow memory.

## Boundary

`rac` is consumed strictly as an external CLI / MCP server on `PATH` — no engine
imports anywhere (DG-ADR-0001). Scoring is deterministic and offline: no
embeddings, no model judge (ADR-066). Vocabulary pools and the id/shard idioms
are reused from the sibling `scale/` member so the two evidence corpora read the
same way.
