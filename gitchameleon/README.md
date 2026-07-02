# gitchameleon — external evidence run (scaffold)

An adapter around **GitChameleon 2.0** (arXiv:2507.12367) — 328 Python
problems, each conditioned on a pinned library version and scored by
**executable unit tests** — asking one question in Lore's terms: *does
grounding an agent in the recorded version-pin decision make its code target
the pinned API instead of the API the model remembers?*

"Code against the superseded API" is the supersession thesis in code form,
and the upstream execution-based scoring is deterministic — the only
recognized external benchmark that fits the ADR-066 posture natively.

**Status: scaffold.** The grounding seam is built and testable offline; the
answering-model call and upstream scoring are the funded-run seam.

## Provenance and licensing

- Upstream code: [github.com/mrcabbage972/GitChameleonBenchmark]
  (Apache-2.0).
- Dataset: [`cabbage972/GitChameleon-2.0`](https://huggingface.co/datasets/cabbage972/GitChameleon-2.0)
  (MIT), fetched on demand by `fetch_dataset.py` — never vendored. Every
  fetch records the dataset revision and a content hash in
  `dataset/provenance.json`; published results must cite that pin.
- `fixtures/sample_problems.json` commits three verbatim rows (MIT, with
  attribution) so the scaffold's tests run offline.

## Design (GCB-ADR-0001)

- **Arms** (DG-ADR-0001 single-variable pattern; held-constant answering
  model): `no_grounding` / `rac` (live-decision retrieval over the example's
  corpus via the shared harness runner — rac strictly as an external CLI) /
  `naive_rag` (refuses until its embedder is pinned at funded-run time).
- **Corpus**: `build_corpus.py` turns each problem into a RAC decision
  artifact — the version pin, its rationale, companion pins, and the
  dataset's documentation links; never the solution, function name, or
  tests — and places it among deterministic distractor pins from other
  examples.
- **Prompt honesty rule**: the task prompt does NOT restate the pinned
  version — version awareness must arrive through grounding, or the
  comparison measures prompt engineering. Consequence: our numbers are an
  arm comparison under this protocol, **not comparable to the upstream
  leaderboard**, which conditions prompts on the version explicitly.
- **Evidence run, never a merge gate**: scoring belongs to the upstream
  harness; nothing here enters gated CI (ADR-066/ADR-097; the
  `external-benchmark-evidence` roadmap in rac-core).

## Scaffold usage (offline, no model calls)

```
python3 fetch_dataset.py                       # dataset/ (gitignored) + provenance pin
python3 build_corpus.py                        # per-example corpora under corpus-build/
python3 run.py --dry-run                       # per-example, per-arm prompt bundles
python3 run.py --dry-run \
  --dataset fixtures/sample_problems.json      # the same, offline from the fixtures
```

`rac` must be on `PATH` for the rac arm (external CLI only — no engine
imports, DG-ADR-0001).

## The funded run (the seam this scaffold leaves open)

1. Pin the answering model (decisiongrounding pins `claude-opus-4-8`) and the
   `naive_rag` embedder (`voyage:voyage-4-large` is the published strong
   baseline there).
2. Feed each dry-run bundle to the answering model; collect completed code
   per (example, arm).
3. Score every arm's solutions with the upstream harness
   (`evaluate --solution-path …` from GitChameleonBenchmark) — its executable
   tests are the scorer; we add nothing.
4. Publish per-arm pass rates with the dataset revision, model pin, and the
   exact reproduction commands; an unfavourable delta is published plainly
   (the SWE-DecisionBench honesty rule applies).

## Local decisions

See [`decisions/`](decisions/) for benchmark-local design records.
