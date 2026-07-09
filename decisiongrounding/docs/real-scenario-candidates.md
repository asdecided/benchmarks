# Real-scenario candidates — graded lexical overlap (roster expansion)

Candidate real PEP/RFC edges for expanding the reportable `scenarios_real/`
roster with **varied lexical overlap** between the task vocabulary and the
distractor pool. This is the reportable complement to the synthetic bank in
`scenarios/` (which is auto-included in the sweep with no pre-registration
impact).

**Status: Step 1 done.** The confirmed corpora below are ingested into
`scenarios_candidates/` (corpus + provenance, no `scenario.json` yet) — see
that directory's `README.md`. They are inert until promoted: nothing under
`scenarios_candidates/` is loaded by the harness or counted by
`tests/test_real_roster.py::PINNED_ROSTER`. Accepting any candidate is a
**deliberate pre-registration event**: it lands together with a `PINNED_ROSTER`
update *and* a new analysis-plan amendment (see
`spec/analysis-plan-amendment-1.md`, which is frozen), and its gold label is
authored **blind** by a third party (CONTRIBUTING rule 1), never by the agent
that proposed the candidate.

## Why graded overlap

The pilot's falsifier verdict rested substantively on one scenario
(`prohibition_language_migration`) whose task vocabulary ("rewrite the orders
API from Go to Python") saturates PEP titles, so `naive_rag` ranked PEP
distractors above the buried prohibition. To learn whether lexical discovery
*generally* collapses at scale — rather than in one over-lexical case — the
roster needs discriminating scenarios spanning **high / medium / low** overlap
with the distractor domain. The measured band is computed by
`scenarios/overlap.py::measured_overlap` (frequency-weighted against the pinned
PEP-title pool); the "estimated band" column below is a pre-ingest guess to be
confirmed after ingest.

## How to ingest a candidate's corpus (blind author fills the gold label)

```bash
# Supersession pair (Replaces / Superseded-By headers carry the edge):
python -m ingest.peps  build --peps <new>,<old> --out scenarios_real/<id>
# RFC supersession (Obsoletes header):
python -m ingest.rfcs  build --rfcs <new>,<old> --out scenarios_real/<id>
# then verify byte-for-byte against the pin:
python -m ingest.peps  verify --out scenarios_real/<id>
```

The ingest tools write `corpus/*.md` + `provenance.json` only. The
`scenario.json` task and `gold_label` are authored blind afterwards, and must
satisfy the offline gate (`context_dump` adheres, `no_grounding` fails) and the
scoring mechanics documented in `spec/scoring-rubric.md`.

## Ingested candidates (Step 1 — confirmed edges)

Each row is staged in `scenarios_candidates/<id>/` with a reproducible corpus +
provenance and **no gold label yet**. Every edge is derived from the artifacts'
own headers at the pin (`Replaces`/`Superseded-By` for PEPs, `Obsoletes` for
RFCs) — none are hand-asserted — and verified with
`python -m ingest.<tool> verify --out scenarios_candidates/<id>`. The overlap
band is an estimate from the topic; it is finalized when the blind task is
written and measured by `scenarios/overlap.py`.

| candidate id | edge (source ← target) | proposed type | est. overlap |
|---|---|---|---|
| `peps_class_creation_supersession` | PEP-0487 ← 0422 | superseded_decision | high |
| `peps_typeis_narrowing_supersession` | PEP-0742 ← 0724 | superseded_decision | high |
| `peps_single_dispatch_supersession` | PEP-0443 ← 0245, 0246 | superseded_decision | high |
| `peps_metadata_v12_supersession` | PEP-0345 ← 0314 (← 0241) | superseded_decision | medium |
| `peps_package_layout_supersession` | PEP-0402 ← 0382 | superseded_decision | medium |
| `peps_hashlib_api_supersession` | PEP-0452 ← 0247 | superseded_decision | medium |
| `peps_packaging_governance_supersession` | PEP-0772 ← 0609 | superseded_decision | low |
| `peps_windows_installer_supersession` | PEP-0773 ← 0397, 0486 | superseded_decision | low |
| `peps_tls_api_supersession` | PEP-0748 ← 0543 | superseded_decision | low |
| `peps_pypi_mirror_supersession` | PEP-0449 ← 0381 | superseded_decision | low |
| `rfc_utf8_supersession` | RFC-3629 ← 2279 | superseded_decision | medium |
| `rfc_tcp_supersession` | RFC-9293 ← 0793 | superseded_decision | low |
| `rfc_ipv6_supersession` | RFC-8200 ← 2460 | superseded_decision | low |

Step 1 deliberately covers **supersession** edges only — they are mechanically
verifiable from headers. Prohibition and conflicting-scoped real scenarios
(which have no machine-readable edge) are a follow-on: the blind author selects
a document carrying a verbatim `MUST NOT`/prohibition and writes the task, using
the synthetic bank's prohibition/conflicting scenarios as the shape reference.

Ingesting more candidates than are ultimately accepted is fine — only those
with a completed blind gold label and a passing offline gate join the roster
(and the roster pin).
