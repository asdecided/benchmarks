# search-artifacts benchmark

Scores the **`search_artifacts`** Lore MCP tool — general ranked retrieval —
via its CLI surface:

```
rac find <query> corpus/ --json [--type <type>]
```

Same `search_index` service and production order as the MCP tool; the
returned ranking is consumed verbatim (no re-sort, no re-rank).

## Run

```
python3 run.py            # human summary
python3 run.py --json     # full scorecard
python3 run.py --check    # CI gate: exit 0 pass, 1 regression, 2 usage error
```

`rac` must be on `PATH` (external CLI only — no engine imports,
DG-ADR-0001).

## Fixture corpus (`SAB-` ids — "Meridian", a collaborative analytics product)

30 artifacts across all five types (9 decisions, 6 requirements, 6 designs,
4 roadmaps, 5 prompts), including two supersession chains, ambiguous sibling
pairs (desktop vs mobile dashboard layout), and cross-type topic clusters
(alerts, connectors, tenancy, realtime).

## Query categories (4 cases each)

- `decision_lookup`, `feature_lookup` — direct retrieval.
- `disambiguation` — sibling pairs; ordering guarded by P@1 and MRR.
- `supersession` — the live member is relevant and the superseded member is a
  hard negative sharing **no token** with the query, so it must never match.
- `cross_type` — one topic word, relevant artifacts of different types.
- `type_filter` — the same search surface under `--type`.

## Scoring and gate

P@k / R@k (`k ∈ {1,3,5}`), MRR (rank-aware — catches within-top-5 ordering
regressions the P@1 / R@5 floors are blind to), macro-averaged; hard
negatives judged against the **full returned list** (`search_artifacts`
serves the full match list, so a superseded decision at rank 6 reaches agents
too). `negative_violations == 0` always; per-category floors on every
category (all have ≥ 4 cases), calibrated from the first green run.

## Local decisions

See [`decisions/`](decisions/) for benchmark-local design records.
