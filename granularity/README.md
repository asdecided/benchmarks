# granularity — retrieval impact of artifact granularity (evidence run)

Measures what ADR-010 (*Documents Are Not Artifacts*) asserts qualitatively:
the same knowledge, rendered two ways, retrieved and scored identically, so
**granularity** is the only variable.

- **artifacts** arm — one valid RAC artifact per file (the RAC model).
- **canon** arm — the *same content* concatenated into two monolithic
  documents (all decisions in one, all requirements in another), one `##`
  heading block per artifact.

Both arms are built from **one deterministic source of truth** (`_model.py`),
so a `(count, seed)` pair fixes every byte of both renderings and the query
set. Reruns on an unchanged corpus are byte-identical (ADR-066); this member is
an **evidence run, never a merge gate** (ADR-066 / ADR-097).

## Why the canon arm is chunk-retrieval by construction

The engine physically cannot represent a canon file as many artifacts, so the
canon arm is framed honestly as what a team actually does with a monolithic
document — chunk it by heading and search the chunks lexically:

- **1 MiB file cap** — a canon of thousands of decisions blows past it.
- **One id per file** — a file carries a single frontmatter identity; a canon
  has no per-decision typed id for `resolve` / `find_decisions` to key on.
- **Duplicate-section collapse** — a file has one `## Status`, one `##
  Decision`; a canon repeating them per block is not a valid artifact.

So the canon arm chunks `decisions-canon.md` by its own `##` headings — the
strongest simple treatment such a document supports (no strawman chunker) —
and ranks the chunks with a **streaming BM25** (`bm25.py`). Its tokenisation is
plainly documented: lowercase, then split on any non-alphanumeric boundary
(`[a-z0-9]+`), the same token-boundary rule the engine's search matches on
(ADR-037). Both arms therefore rank on the same lexical family; granularity and
typing are the only variables. The canon arm has **no liveness or supersession
logic** — a document carries no typed identity for a live filter to read — and
that absence is exactly what the benchmark measures.

## What the arms do differently

The corpus seeds ~15% of decisions into supersession chains: a superseded
ancestor carries a `## Status: Superseded` the engine's live filter reads, and
its live head carries a real `## Supersedes` edge that `rac relationships
--validate` resolves. Chain members share topic vocabulary, so a query built
from those terms lexically matches **both** the superseded ancestor and the
live head — only liveness knowledge picks the right one.

- The **artifacts** arm answers `supersession` / `related` cases with
  `find_decisions` (the typed live-decision tool, served warm from `rac mcp
  --root artifacts/ --index`, ADR-100/101), whose filter the per-file
  `Superseded` status enables — so a superseded ancestor is never returned.
- The **canon** arm cannot filter; its BM25 ranks a superseded block on its
  text like any other, so superseded ancestors surface in results.

## Query classes (`queries.json`, ADR-097 family shape)

`{"id", "class", "query", "must_return": [live id], "must_not_return":
[superseded ancestor ids...]}`

- `topic` — a standalone live decision by its own terms; no negatives. A plain
  retrieval-quality comparison (the canon arm can win it; the scorecard reports
  that honestly).
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
scorecard reports every metric for both arms with a signed delta, in both
directions honestly.

## Run the ladder

```
export PATH=/path/to/rac/venv/bin:$PATH        # rac (with `mcp --index`) on PATH

python granularity/build_corpus.py  --count 1000 --out DIR --seed 42 --manifest
python granularity/build_queries.py --count 1000 --out DIR --seed 42
python granularity/run.py --corpus DIR          # writes DIR/results.json + a table
```

The `--count` ladder is 1k / 10k / 100k, aligned with the scale member, for a
quality-versus-size curve per arm. `build_corpus.py` self-checks the per-file
variant with `rac validate` and `rac relationships --validate`; both the
builder and the runner stream (one artifact / one chunk in memory at a time),
so nothing holds a whole canon and the 100k rung does not blow memory.

## Boundary

`rac` is consumed strictly as an external CLI / MCP server on `PATH` — no
engine imports anywhere (DG-ADR-0001). Scoring is deterministic and offline: no
embeddings, no model judge (ADR-066). Vocabulary pools and the id/shard idioms
are reused from the sibling `scale/` member so the two evidence corpora read
the same way.
