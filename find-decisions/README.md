# find-decisions benchmark

Scores the **`find_decisions`** Lore MCP tool — the live-decision query with
the structural supersession defense — via its CLI surface:

```
rac find <query> corpus/ --decisions --json
```

`--decisions` filters to live decisions (Accepted, non-retired, ADR-067)
before ranking. This tool is the supersession defense: a superseded,
deprecated, or proposed decision must never reach an agent from this surface,
*even when it is the lexically best match for the query*. Until this suite,
that defense had no benchmark coverage anywhere.

## Run

```
python3 run.py            # human summary
python3 run.py --json     # full scorecard
python3 run.py --check    # CI gate: exit 0 pass, 1 regression, 2 usage error
```

`rac` must be on `PATH` (external CLI only — no engine imports,
DG-ADR-0001).

## Fixture corpus (`FDB-` ids — "Beacon", an API platform)

- A three-deep supersession chain (signed cookie → Redis → stateless JWT
  sessions) where each superseded member is the lexically best match for its
  era's vocabulary.
- A two-deep chain (fixed window → sliding window rate limits).
- A deprecated decision (XML payloads) and a proposed decision (GraphQL
  gateway), both lexically strong for their topics.
- Non-decision distractors (a requirement, a design) that are the lexically
  best match for `type_scope` queries.

## Scoring and gate

P@k / R@k (`k ∈ {1,3,5}`), MRR, macro-averaged; hard negatives judged against
the **full returned list** — a retired decision at rank 6 still reaches an
agent, so it still fails the gate. `negative_violations == 0` is always
gated; floors are calibrated from the first green run (committed baseline).
`type_scope` has 2 cases and carries no per-category floor: with 2 cases the
metrics quantize to {0, 0.5, 1.0} and a 0.9 floor would be theater.

## Local decisions

See [`decisions/`](decisions/) for benchmark-local design records.
