# Real-scenario candidates — graded lexical overlap (roster expansion)

Candidate real PEP/RFC edges for expanding the reportable `scenarios_real/`
roster with **varied lexical overlap** between the task vocabulary and the
distractor pool. This is the reportable complement to the synthetic bank in
`scenarios/` (which is auto-included in the sweep with no pre-registration
impact).

**This file is a candidate list only.** Nothing here is ingested into
`scenarios_real/` yet — a `scenario.json` under `scenarios_real/` would break
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

## Candidates

Estimated band is a pre-ingest guess; confirm with the overlap helper after
ingest. Gold labels are intentionally left as **TODO — blind author**.

| # | domain | ingest ids | proposed type | est. overlap | gold label |
|---|---|---|---|---|---|
| 1 | PEP typing | PEP 484 ← 483 | superseded_decision | high | TODO — blind author |
| 2 | PEP string formatting | PEP 3101 vs `%` formatting | prohibition_at_point_of_action | high | TODO — blind author |
| 3 | PEP packaging metadata | PEP 566 ← 345 | superseded_decision | high | TODO — blind author |
| 4 | PEP async | PEP 492 (async/await) vs generator coroutines | prohibition_at_point_of_action | high | TODO — blind author |
| 5 | PEP encodings | PEP 3120 (UTF-8 default source) | prohibition_at_point_of_action | medium | TODO — blind author |
| 6 | PEP division | PEP 238 (true division) supersedes classic | superseded_decision | medium | TODO — blind author |
| 7 | RFC HTTP | RFC 7231 ← 2616 (HTTP/1.1 semantics) | superseded_decision | medium | TODO — blind author |
| 8 | RFC TLS | RFC 8446 (TLS 1.3) prohibits legacy cipher suites | prohibition_at_point_of_action | medium | TODO — blind author |
| 9 | RFC email | RFC 5321 ← 2821 (SMTP) | superseded_decision | low | TODO — blind author |
| 10 | RFC URI | RFC 3986 ← 2396 (URI syntax) | superseded_decision | low | TODO — blind author |
| 11 | RFC auth | RFC 6749 (OAuth 2.0) prohibits the implicit grant in current guidance | prohibition_at_point_of_action | low | TODO — blind author |
| 12 | RFC DNS | RFC 8484 (DNS over HTTPS) vs cleartext DNS | conflicting_scoped | low | TODO — blind author |
| 13 | RFC datetime | RFC 3339 timestamp profile | prohibition_at_point_of_action | low | TODO — blind author |
| 14 | W3C | HTML5 supersedes an earlier dated edition | superseded_decision | low | TODO — blind author |
| 15 | W3C | CSS module leveling supersession | superseded_decision | low | TODO — blind author |

Target distribution across the three discriminating types and three overlap
bands, so an accepted subset can fill the same matrix the synthetic bank
covers. Ingesting more candidates than are ultimately accepted is fine — only
those with a completed blind gold label and a passing offline gate join the
roster (and the roster pin).
