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

39 artifacts across all five types (18 decisions, 6 requirements, 6 designs,
4 roadmaps, 5 prompts), including two supersession chains, ambiguous sibling
pairs (desktop vs mobile dashboard layout), cross-type topic clusters (alerts,
connectors, tenancy, realtime), and a nine-decision adversarial graph cluster.

## Query categories (4 cases each)

- `decision_lookup`, `feature_lookup` — direct retrieval.
- `disambiguation` — sibling pairs; ordering guarded by P@1 and MRR.
- `supersession` — the live member is relevant and the superseded member is a
  hard negative sharing **no token** with the query, so it must never match.
- `cross_type` — one topic word, relevant artifacts of different types.
- `type_filter` — the same search surface under `--type`.
- `graph_boost_gate` — a weak lexical hub whose inbound graph rank would beat
  the focused policy under the ungated ADR-078 formula; the 0.85 lexical floor
  must clamp it and keep the focused policy at rank 1.

## Scoring and gate

P@k / R@k (`k ∈ {1,3,5}`), MRR (rank-aware — catches within-top-5 ordering
regressions the P@1 / R@5 floors are blind to), macro-averaged; hard
negatives judged against the **full returned list** (`search_artifacts`
serves the full match list, so a superseded decision at rank 6 reaches agents
too). `negative_violations == 0` always; per-category floors on every
category (all have ≥ 4 cases), calibrated from the first green run.

The graph-gate category also has a black-box counterfactual test. It consumes
`decided find --json --explain` and proves all three properties together: the
old ungated formula would place the hub first, the production result keeps the
strong lexical policy first, and its explanation reports
`graph_floor_ratio: 0.85` with the hub `clamped`. Explain mode is separately
checked for determinism and unchanged result membership.

`python3 ratio_sweep.py` is a non-gating tuning diagnostic. It replays the
documented RRF formula over production explain components at ratios 0.75,
0.80, 0.85, 0.90, and 0.95. The committed test requires 0.85 to be the first
grid point at which every adversarial case restores the focused policy to
rank 1. The scorecard itself never consumes this counterfactual order.

## Local decisions

See [`decisions/`](decisions/) for benchmark-local design records.
