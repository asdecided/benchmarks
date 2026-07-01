# get-related benchmark

Scores the **`get_related`** Lore MCP tool — relationship-edge retrieval —
via its closest CLI surface:

```
rac relationships corpus/ --json      # corpus-wide typed edge map
rac resolve <id> corpus/ --json       # id -> path (harness plumbing)
rac index corpus/ --json              # path -> id for edge sources (plumbing)
```

Each case names an artifact and declares its **exact expected incoming AND
outgoing edge sets** — the outgoing direction was previously unguarded —
scored as set membership over the corpus-wide relationship map. The harness
inverts the map to name incoming-edge sources; it never re-orders or re-ranks
anything the tool returned.

## Run

```
python3 run.py            # human summary
python3 run.py --json     # full scorecard
python3 run.py --check    # CI gate: exit 0 pass, 1 regression, 2 usage error
```

`rac` must be on `PATH` (external CLI only — no engine imports,
DG-ADR-0001).

## Fixture corpus (`GRB-` ids — "Harbor", a deployment platform)

Eight artifacts forming a known graph: a hub decision with four incoming
edges and a `supersedes` outgoing edge, a superseded decision whose only
incoming edge is the superseding one, bidirectional and outgoing-only nodes,
and one fully isolated artifact.

## Scoring and gate

Conformance pass-rate gated at 1.0 with zero tolerance (edge sets either
match their declaration or they do not), plus `negative_violations == 0`: a
`must_not_return` id appearing in either returned edge set is a violation.

## Recorded limitation (do not silently drop)

The MCP tool's `depth > 1` neighborhood expansion and the ADR-033 response
budget / truncation markers are invisible to the CLI surface. They are out of
scope for this CLI-driven v1 and recorded as the deferred MCP-stdio harness
workstream in the `tool-benchmarks` roadmap and rac-core ADR-097.

## Local decisions

See [`decisions/`](decisions/) for benchmark-local design records.
