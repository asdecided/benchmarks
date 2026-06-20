# Independent Scenario-Authoring Protocol (for a third-party model/agent)

This is a **portable prompt**. Paste everything under "PROMPT" into a *different*
model or coding agent (e.g. an OpenAI model) and point it at a fresh checkout of
this repository. Its purpose is to make scenario authorship **independent of the
benchmark's sponsor**: a party that did not build the grounding layer under test
selects the real decisions and writes the gold labels.

## What independence this buys (and what it does not)

The benchmark already removes two biases: the answering model is **arm-agnostic**
(it never sees which arm assembled its context) and scoring is **deterministic**
(no LLM judge to lean). The remaining sponsor-side degree of freedom is *which*
real edges become scenarios and *how* the gold label is phrased. An independent
author closes that gap.

It does **not** make the layer-under-test independent — that is still the
sponsor's code. The honest claim after this is: *"the test set was authored by an
independent model from public sources under a frozen protocol,"* not *"the whole
benchmark is third-party."* State it that way.

To keep the author neutral, the prompt below **does not name or describe any
arm** and instructs the author not to read `providers/`. It must not try to make
any retrieval strategy win or lose.

---

## PROMPT

You are an independent test-scenario author for a benchmark that measures whether
an AI coding assistant, when given a set of a software team's prior decisions as
context, proposes a change that **adheres to those decisions**. You did not build
this benchmark and have no stake in any result. Work only from public sources and
the rules below.

**Do not read `providers/` or `scoring/scorer.py`.** You must not tailor
scenarios to any particular way of selecting context; you don't know which
strategies are being compared, and engineering for one would invalidate the test.

### Your task

Add `N` new real test scenarios under `scenarios_real/` (start with `N=5`). Each
scenario is a directory containing:

- `corpus/` — verbatim public decision documents, ingested deterministically.
- `provenance.json` — written by the ingest tool (source URLs, per-document
  sha256, derived edges).
- `scenario.json` — the task and the **gold label** (the correct answer), which
  you author.

### Hard integrity rules (a scenario that breaks any of these is invalid)

1. **Real and public-derived only.** The corpus must be unedited public documents
   (Python PEPs, IETF RFCs, W3C Recommendations, or similar). Never hand-write or
   paraphrase decision prose. Use the provided ingest tools, which pin sources:
   - PEPs: `python -m ingest.peps build --peps <nums> --out scenarios_real/<id>`
     (pinned to one immutable `python/peps` commit).
   - RFCs: `python -m ingest.rfcs build --rfcs <nums> --out scenarios_real/<id>`
     (RFCs are immutable; pinned by sha256).
   If you use a source without an ingest tool, you must write a deterministic,
   pinned ingester for it the same way (verbatim text + provenance with sha256);
   do not paste prose by hand.
2. **The relationship must come from the document's own machine-readable
   metadata, never from prose interpretation.** Supersession = a PEP `Replaces` /
   `Superseded-By` header or an RFC `Obsoletes` header. A prohibition = an
   explicit normative clause present **verbatim** in the text (e.g. a literal
   "MUST NOT" / "is prohibited"). If you cannot point to the exact bytes, do not
   use it.
3. **Author the gold label blind.** Decide the correct answer from the source
   text alone, before running anything. In `gold_label.rationale`, quote the
   governing clause/header verbatim and end with a sentence stating you authored
   it blind to any benchmark output and that no run had been executed.
4. **Neutral, plausible difficulty.** Choose cases where a competent assistant
   could genuinely err (the retired option is still attractive; the prohibition
   is easy to miss). Do not engineer them toward or away from any retrieval
   method.
5. **Deterministic & reproducible.** After building, `python -m ingest.<tool>
   verify --out scenarios_real/<id>` (or your pinned equivalent) must reproduce
   the corpus byte-for-byte.

### The two scenario types to author

- `superseded_decision`: the corpus holds a **retired** decision (Status
  `Superseded` / obsoleted) and its **live successor**. The task proposes
  following the retired one. Gold: `verdict="prohibited"`,
  `governing_decision`=the successor id; the retired id is what an adherent agent
  must NOT follow.
- `prohibition_at_point_of_action`: the corpus holds a decision with an explicit
  verbatim normative prohibition. The task proposes doing the forbidden thing.
  Gold: `verdict="prohibited"`, `governing_decision`=that document id.

### `scenario.json` shape

Conform exactly to `schema/scenario.schema.json` (validate against it). Required
top-level fields: `scenario_id`, `version` ("1.0.0"), `scenario_type`,
`expected_tie` (false for these two types), `corpus.artifacts[]` (each `id`,
`type":"decision"`, `path`; the successor also lists `supersedes:[...]`), `task`
(`prompt`, `proposed_action`), `binding_decisions` (the governing id(s);
`[]` only for negative controls), `relationships[]` (the `supersedes` edge(s);
`[]` for a pure prohibition), and `gold_label` (`verdict`, `governing_decision`,
`prohibited_actions[]`, `required_actions[]`, `rationale`). Study any existing
directory under `scenarios_real/` for the exact format, but pick **different**
documents — do not duplicate an existing edge.

### Acceptance gates (every new scenario must pass all)

```bash
# 1. Loads and schema-validates:
python -c "from scenarios.loader import load_scenarios; load_scenarios('scenarios_real')"
# 2. Reproduces from the pin:
python -m ingest.<tool> verify --out scenarios_real/<id>
# 3. Is genuinely discriminating and the gold label is consistent:
python -m pytest -q tests/test_real_pilots.py
```

`test_real_pilots.py` enforces, for every scenario, that the gold label names an
in-corpus governing decision and that a context-complete answer adheres while a
context-empty answer does not. If a new scenario fails it, the gold label or the
corpus is wrong — fix it, do not weaken the test.

### Deliverable

The new scenario directories plus a short `AUTHORS-NOTE.md` listing, per
scenario: the source documents and their URLs, the exact governing
header/clause you relied on (quoted), and one sentence on why the gold verdict
follows. Do not modify `providers/`, `scoring/`, or any existing scenario.

---

## Reviewing what the third party produced

When the independent author returns scenarios, the sponsor's only job is to
**verify, not reshape**: run the three acceptance gates above, confirm each cited
header/clause exists verbatim in the source, and confirm no `providers/` or
`scoring/` files were touched. Merge as-authored or reject with a reason; do not
edit the gold labels. Record the authoring model + date alongside the scenarios.
