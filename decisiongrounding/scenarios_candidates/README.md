# Scenario candidates (staging area — NOT the reportable roster)

Real, pinned corpora ingested for the graded-overlap roster expansion, held
here **before** they join the frozen `scenarios_real/` roster. Each directory
has `corpus/*.md` + `provenance.json` (reproducible from the pin) but **no
`scenario.json`** — the task and gold label are authored later, blind
(CONTRIBUTING rule 1), ideally by an independent third party.

Nothing here is loaded by the harness or counted by the roster:
`scenarios/loader.py::load_scenarios` and `tests/test_real_roster.py` only see
directories containing a `scenario.json`. So these corpora are inert until
promoted.

## What's staged (Step 1 of the expansion)

13 real supersession edges, all verified to reproduce from their pins
(`python -m ingest.peps|rfcs verify --out scenarios_candidates/<id>`). The
overlap band is an *estimate* until the blind task is written and measured by
`scenarios/overlap.py`.

| candidate id | edge (source supersedes target) | est. overlap |
|---|---|---|
| `peps_class_creation_supersession` | PEP-0487 ← PEP-0422 | high |
| `peps_typeis_narrowing_supersession` | PEP-0742 ← PEP-0724 | high |
| `peps_single_dispatch_supersession` | PEP-0443 ← PEP-0245, PEP-0246 | high |
| `peps_metadata_v12_supersession` | PEP-0345 ← PEP-0314 (← PEP-0241) | medium |
| `peps_package_layout_supersession` | PEP-0402 ← PEP-0382 | medium |
| `peps_hashlib_api_supersession` | PEP-0452 ← PEP-0247 | medium |
| `peps_packaging_governance_supersession` | PEP-0772 ← PEP-0609 | low |
| `peps_windows_installer_supersession` | PEP-0773 ← PEP-0397, PEP-0486 | low |
| `peps_tls_api_supersession` | PEP-0748 ← PEP-0543 | low |
| `peps_pypi_mirror_supersession` | PEP-0449 ← PEP-0381 | low |
| `rfc_utf8_supersession` | RFC-3629 ← RFC-2279 | medium |
| `rfc_tcp_supersession` | RFC-9293 ← RFC-0793 | low |
| `rfc_ipv6_supersession` | RFC-8200 ← RFC-2460 | low |

All edges are derived from the artifacts' own `Replaces` / `Superseded-By`
(PEP) or `Obsoletes` (RFC) headers at the pin — none are hand-asserted.

## Promoting a candidate into the roster (Steps 2–3)

1. **Author `scenario.json` blind** (task + `gold_label`), per
   `spec/external-scenario-request-graded-overlap.md`. Must pass the offline
   gate (`context_dump` adheres, `no_grounding` fails) and match its declared
   `lexical_overlap` band under `scenarios/overlap.py`.
2. `git mv scenarios_candidates/<id> scenarios_real/<id>` (provenance is
   path-independent; re-run `verify` afterward).
3. Extend `tests/test_real_roster.py::PINNED_ROSTER` and its per-domain counts,
   and land a new `spec/analysis-plan-amendment-*.md` re-registering the
   enlarged roster — the deliberate pre-registration event. Amendment-1 and
   amendment-2 stay frozen.
