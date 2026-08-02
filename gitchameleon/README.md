# gitchameleon — external evidence run (scaffold)

An adapter around **GitChameleon 2.0** (arXiv:2507.12367) — 328 Python
problems, each conditioned on a pinned library version and scored by
**executable unit tests** — asking one question in Lore's terms: *does
grounding an agent in the recorded version-pin decision make its code target
the pinned API instead of the API the model remembers?*

"Code against the superseded API" is the supersession thesis in code form,
and the upstream execution-based scoring is deterministic — the only
recognized external benchmark that fits the ADR-066 posture natively.

**Status: run-ready.** The grounding seam and the full solutions → score →
stats pipeline are built and testable offline (the `offline-stub` backend);
only the funded answering calls and the upstream execution remain. This run's
per-arm pass rate is SWE-DecisionBench's second co-primary outcome,
**decision-conditioned resolution** (GCB-ADR-0002).

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
  model): `no_grounding` / `asdecided` (live-decision retrieval over the
  example's corpus via the shared harness runner — As Decided strictly as an
  external CLI) / `naive_rag` (embedding retrieval over the identical corpus, pinned to
  `voyage-4-large`, with query/document input types and cosine ranking).
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
python3 fetch_dataset.py --revision 799a6a33e572a07a8985914e7251f5dea54b0ac4
python3 build_corpus.py                        # per-example corpora under corpus-build/
python3 run.py --dry-run                       # no_grounding + asdecided bundles
python3 run.py --dry-run \
  --dataset fixtures/sample_problems.json      # the same, offline from the fixtures
```

`decided` must be on `PATH` for the `asdecided` arm (external CLI only — no engine
imports, DG-ADR-0001).

## The funded run (GCB-ADR-0002 — the resolution co-primary pipeline)

The pre-registered analysis and falsifier for this outcome live in
`../decisiongrounding/spec/analysis-plan-amendment-1.md` (H2). Each step is
resumable in isolation:

1. Build all three arm bundles. The answering model is pinned to
   `claude-opus-4-8`; the baseline embedder is pinned to
   `voyage-4-large` (GCB-ADR-0003). Every frozen input is recorded in
   [`run-config.json`](run-config.json):

   ```
   VOYAGE_API_KEY=... python3 run.py --dry-run \
     --arms no_grounding,asdecided,naive_rag --out out/bundles.jsonl
   ```

2. Run a one-example-per-arm shakedown, inspect it, then answer every bundle.
   `--resume` appends only missing example IDs, flushes every completion, and
   records hashes of the exact prompt and grounding injected into the model:

   ```
   python3 run.py solutions --bundles out/bundles.jsonl \
     --answering claude --seed 0 --limit 1 --out out/shakedown
   python3 run.py solutions --bundles out/bundles.jsonl \
     --answering claude --seed 0 --resume --out out/solutions
   ```

   writes `out/solutions/solutions-<arm>.jsonl` in exactly the upstream
   `Solution` shape (`example_id` + `answer`; the provenance extras are
   ignored by upstream). `--answering offline-stub` exercises the plumbing
   keylessly; `litellm:<alias>` targets an OpenAI-compatible gateway.
3. Score each arm's file with the upstream harness — its executable tests
   are the scorer; we add nothing. Clone GitChameleonBenchmark at commit
   `3a1b6045a6b2a276bd24d715589cb041f8eccb93`, build its Docker image locally
   from that checkout, and run
   `evaluate --solution-path out/solutions/solutions-<arm>.jsonl` (budget the
   per-version dependency installs). It writes
   `solutions-<arm>_eval_results.csv` next to each solution file.
4. Normalize the verdicts into paired resolution records
   (`schema/resolution_record.schema.json`) and run the pre-registered
   paired analysis:

   ```
   python3 run.py score --arm asdecided \
     --eval-results out/solutions/solutions-asdecided_eval_results.csv \
     --answering-model claude-opus-4-8 --upstream-harness <commit> \
     --out out/resolution_records.jsonl
   python3 run.py score --arm no_grounding --eval-results … --append …
   python3 run.py stats --records out/resolution_records.jsonl \
     --require-arms no_grounding,asdecided,naive_rag
   ```

5. Publish the records, per-arm pass rates, and stats with the dataset
   revision, model pin, upstream-harness commit, and the exact reproduction
   commands; an unfavourable delta is published plainly (the
   SWE-DecisionBench honesty rule applies to both co-primary outcomes).

## Local decisions

See [`decisions/`](decisions/) for benchmark-local design records, including
the funded-run execution contract and pinning rationale (GCB-ADR-0003).
