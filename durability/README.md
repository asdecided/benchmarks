# durability — does the structure retrieval-safety depends on survive editing?

The granularity member settled the retrieval question and found a **null**:
with an identical ranker, splitting knowledge into typed per-file artifacts does
not improve lexical retrieval, and a status-aware parser over a *well-formed*
canon recovers the superseded-decision defence completely. So the case for
per-artifact splitting is not retrieval quality. It is **governance**: the
artifact model's status and reference structure is a *validated contract*, while
a canon document's status lines are an *unenforced convention* a single sloppy
edit can silently break.

This member measures that — the **enforceability under realistic editing** an
adopter weighing artifacts against canon documents actually needs. It is an
**evidence run, never a merge gate** (ADR-066 / ADR-097); it drives `rac` only
as an external CLI / MCP server on `PATH` (DG-ADR-0001) and imports no engine
code. Reruns on unchanged inputs are byte-identical.

It reuses the granularity member's machinery wholesale: `_model.py` +
`build_corpus.py` build the one deterministic source of truth in both renderings
(per-file artifacts and a monolithic canon), `build_queries.py` builds the query
set, `bm25.py` provides the status-aware canon retrieval, and `arms.py` provides
the typed engine arm (`rac mcp --index` → `find_decisions`).

## The claim under test

> Per-artifact splitting does not win on retrieval; it wins because the
> structure retrieval-safety depends on is **enforceable**. A canon's status
> convention rots under sloppy edits and a broken block boundary corrupts
> neighbouring decisions; the artifact model's contract is caught by a gate that
> already ships — and even *ungated*, an invalid status cannot masquerade as
> live.

Two failure modes are measured, both "lower is better":

- **leaks** — a superseded decision surfaces (a `must_not_return` id returned
  anywhere). The safety defence has failed silently.
- **misses** — a live head is no longer returned (a `must_return` id dropped).
  A decision has become unreachable.

## The four conditions (all reported at equal prominence)

The roadmap is explicit that the **ungated artifact arm is reported with the
same prominence as the gated arm**: if ungated artifacts rot at canon rates, the
report must say the *gate*, not the *split*, carries the value. So four
conditions run the identical edit stream and are printed side by side:

| condition | rendering | enforcement |
| --- | --- | --- |
| `gated-artifacts` | per-file artifacts | `rac validate` + `relationships --validate` each round; edits whose files are flagged are **reverted** (a merge gate) |
| `ungated-artifacts` | per-file artifacts | **none** — edits land regardless (nobody runs the gate) |
| `canon` | monolithic document | none — the linter is *reported but never blocks*, mirroring reality: no team runs a bespoke linter as a required gate |
| `canon-linter-gated` | monolithic document | the linter as a gate, for **symmetry** — what a best-effort canon check *would* recover |

What the curves show, and the honest reading:

- **The split alone stops the leak.** An invalid status is not a valid decision
  status, so the engine drops the record rather than serving it live — *ungated*
  artifacts take **zero leaks**. The canon, whose `Superseded` is just text a
  filter matches, leaks.
- **Only the gate stops the miss.** Frontmatter identity damage drops a
  decision from the index; *ungated* artifacts take misses at canon rates. The
  `gated-artifacts` arm reverts the damaging edit and stays clean. So the gate,
  not the split, carries the miss-defence — and the report says so.
- **The canon rots on both axes with no enforcement.** `canon-linter-gated`
  shows a bespoke linter *would* recover most of it — but it is not a gate
  anyone runs, and it still cannot catch a dangling reference (see the ceiling).

## The edit taxonomy (a recorded assumption — `TAXONOMY_VERSION`)

`edits.py` is a deterministic seeded engine: every edit is a pure function of
`(seed, round, seq)`. A **logical** edit is applied identically to both
renderings — the per-file artifact *and* the corresponding canon `##` block for
the same decision.

**Clean edits** (the realistic churn a corpus takes) target decisions no query
exercises, so they never rewrite a query's own ground truth and stay
metric-neutral: `reword-context`, `append-consequence`, `supersede` (retire a
live decision with a correctly-linked successor — this *improves* safety),
`add-cross-reference`.

A parameterised **sloppy fraction `p`** lands one **break class** instead of the
clean form. The leak-bearing breaks land on the superseded ancestors the query
set actually exercises, and `boundary-break` on a live head the query set
expects back — so the curve measures breakage that *reaches a reader*, not
breakage in corpus regions no query touches. This targeting is stated for
critique, not tuned to flatter either rendering.

| break class | canon effect | artifact effect |
| --- | --- | --- |
| `malformed-status` | `Superseded` → `superceded` / `SUPERSEDED (see v2)` / `Status : Superseded`; the live-filter misses it → **leak** | not a valid decision status → engine drops the record (no leak); `rac validate` flags `invalid-decision-status` |
| `heading-slip` | `### Status` → `#### Status`; the filter keys on the exact heading → **leak** | `## Status` → `### Status`; the engine parser is level-tolerant → no effect |
| `boundary-break` | the target's `## ` heading is stripped → it merges into its predecessor: its id is unreachable and the predecessor is contaminated (**blast radius > 1**) | frontmatter identity damage (`id:` → `id`) drops the *same* target from the index (**blast radius 1**) |
| `duplicate-id` | a new block heading reuses an existing id | a new file whose frontmatter id duplicates a live one |
| `dangling-ref` | a `Supersedes` line targets an id that exists nowhere | same |

## The linter's honest ceiling

`linter.py` is the **strongest cheap** deterministic canon check — what a team
could write over a monolithic document *without* rebuilding the engine: per-block
status well-formedness, heading discipline, block-boundary sanity, and a
full-scan duplicate-id detector. The detectability matrix reports **measured**
detection, not asserted inability — the linter *earns* four of the five classes.

The one it cannot: **`dangling-ref`**. A `- RAC-…` under a supersedes section may
point to a decision that lives in *another* canon (the requirements document), in
a per-file-only rendering, or be legitimate under the schema's relationship
semantics. The linter has no frontmatter identity, no schema registry, and no
relationship graph, so flagging every unresolved id would false-positive on every
valid cross-document reference. Resolving the target *is* reimplementing the
engine — so the matrix records this class as undetected, and that is the honest
boundary where free contract checks end and bespoke tooling begins.

Symmetrically, the artifact gate misses `heading-slip` — but that break is
*harmless* on the artifact side (the parser is level-tolerant), so nothing rots.

## What it measures

1. **Safety decay** — after each of `R` rounds at each sloppy rate in
   `{0.01, 0.05, 0.10}`, both retrievals are re-run in all four conditions and
   leaks / misses are recorded per round.
2. **Detectability matrix** — each break class injected `K` times in isolation;
   detection rate of the artifact gates (`rac validate` +
   `relationships --validate`, from actual exit findings) versus the canon
   `linter`, per class.
3. **Merge conflicts** — `N` seeded concurrent-edit pairs under deterministic
   three-way `git merge-file`, at controlled block gaps: canon forces a
   shared-file merge on 100% of concurrent pairs; per-artifact isolates all but
   genuine same-artifact edits. Reported with the analytical same-artifact
   collision rate for context.
4. **Blast radius** — decisions corrupted per `boundary-break`: a
   chunk-count / contamination delta in canon versus exactly one in the
   artifacts.

Every curve is reported at each sloppy rate and seed; **no delta is claimed
unless its sign is stable across seeds** (`--seeds`).

## Running

```bash
# single seed → results.json + tables on stdout
python durability/run.py --count 1000 --seed 42

# three seeds → variance.json + headline-delta sign consistency
python durability/run.py --seeds 42,43,44 --count 1000
```

Flags: `--rounds` (default 5), `--edits-per-round` (100), `--inject-k` (20),
`--merge-pairs` (200), `--out`. `rac` and `git` must be on `PATH`. A full 1k
three-seed run completes in a few minutes.

## Scorecard shape (ADR-097 family form)

```jsonc
{
  "schema_version": 1,
  "model_version": 2,
  "metrics": {
    "safety_decay":    { "<rate>": { "<condition>": { "per_round": [ … ] } } },
    "detectability":   { "<break class>": { "artifacts": …, "canon_linter": … } },
    "merge_conflicts": { "per_gap": …, "totals": …, "canon_shared_file_rate": … },
    "blast_radius":    { "canon": …, "artifacts": … }
  },
  "metadata": { "count", "seed", "rounds", "edits_per_round", "rates",
                "taxonomy_version", "engine_version", … }
}
```

Floats and counts are integers or fixed-precision; `sort_keys` serialisation is
byte-identical across reruns on unchanged inputs (ADR-066). Multi-seed output
adds a `sign_consistency` block over the headline deltas and the full `per_seed`
scorecards.

## Files

- `edits.py` — the deterministic seeded edit engine (taxonomy + break classes).
- `linter.py` — the strongest cheap canon linter, and its documented ceiling.
- `run.py` — the measurement driver (four conditions, three pillars, blast
  radius) and the family scorecard.
- `README.md`, `pyproject.toml`, `LICENSE`, `NOTICE`.

## Related decisions

ADR-010 (Documents Are Not Artifacts), ADR-063/065/066 (untrusted content, human
PR review as the trust boundary, deterministic offline scoring), ADR-097
(benchmark family contract). Roadmap: `durability-benchmark`
(`granularity-benchmark` predecessor).
