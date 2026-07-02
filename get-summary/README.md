# get-summary benchmark

Scores the **`get_summary`** Lore MCP tool — the repository portfolio
summary — via its CLI surface:

```
rac portfolio <root> --json
```

## Run

```
python3 run.py            # human summary
python3 run.py --json     # full scorecard
python3 run.py --check    # CI gate: exit 0 pass, 1 regression, 2 usage error
```

`rac` must be on `PATH` (external CLI only — no engine imports,
DG-ADR-0001).

## Fixture corpora (`GSB-` ids — "Quill", a notes product)

- `corpus/` — a known composition: 3 decisions, 2 requirements, 2 designs,
  1 roadmap, 1 prompt (9 artifacts).
- `corpus-empty/` — an empty corpus (a `.gitkeep` only), for the empty-shape
  case.

## Conformance cases

- `counts` — `artifacts.total` and `artifacts.by_type` match the fixture
  composition exactly, across all five types.
- `empty_corpus` — the empty-corpus shape (`empty: true`, zero counts).
- `stability` — two consecutive runs emit byte-identical payloads, on both
  the populated and the empty corpus.

Conformance is gated at 1.0 with zero tolerance.

## Local decisions

See [`decisions/`](decisions/) for benchmark-local design records.
