# get-artifact benchmark

Scores the **`get_artifact`** Lore MCP tool — exact-id resolution — via its
CLI surface:

```
rac resolve <id> corpus/ --json
```

## Run

```
python3 run.py            # human summary
python3 run.py --json     # full scorecard
python3 run.py --check    # CI gate: exit 0 pass, 1 regression, 2 usage error
```

`rac` must be on `PATH` (external CLI only — no engine imports,
DG-ADR-0001).

## Fixture corpus (`GAB-` ids — "Atlas", a documentation service)

Seven files across the five artifact types, including a deliberate duplicate
pair: two distinct files answering to one canonical id, so the resolver's
duplicate contract can be asserted rather than assumed.

## Conformance cases

- `exact_id` — canonical-id hit; asserts the stable payload fields
  (`schema_version`, `id`, `type`, `title`, `path` — ADR-007).
- `case_insensitive` — lower/mixed-case lookups resolve to the canonical id.
- `legacy_alias` — filename-stem aliases keep resolving (identity migration
  compatibility).
- `duplicate` — the duplicated id reports `error: duplicate` with every path
  and exit 1; it is never silently resolved by path order.
- `not_found` — unknown ids report `error: not-found` with exit 1.

Conformance is gated at 1.0 with zero tolerance: a resolution contract is
either honoured or it is not.

## Recorded limitation

The MCP `get_artifact` payload's provenance enrichment is not present in the
`rac resolve --json` payload of the current CLI, so provenance-field
conformance is out of scope for this CLI-driven v1 and recorded as part of
the deferred MCP-stdio harness workstream (see the `tool-benchmarks` roadmap
in rac-core).

## Local decisions

See [`decisions/`](decisions/) for benchmark-local design records.
