---
schema_version: 1
id: DG-KVMS87QZDXJY
type: decision
tags: [ui, dashboard, rendering, architecture]
---
# Progressive Enhancement, Not Client-Side Rendering, for the Dashboard

## Context

The results dashboard is server-rendered: `runner/dashboard.py` (`build_dashboard`)
emits a complete HTML page, and the charts are deterministic SVG produced in
`scoring/charts.py` — no matplotlib, no CDN. Two consumers share that renderer:
the live server (`runner/ui.py`, the `ui` command) and a static-snapshot
generator (`scripts/dashboard.py`) whose `results/published/index.html` is a
committable, diffable, offline-viewable artifact.

We want more interactivity — sort/filter/search the tables, isolate one arm on a
curve, and refresh results without losing place. The question is whether to keep
server-side rendering (SSR) and layer JavaScript on top, or move to full
client-side rendering (CSR): ship JSON from the API and build the tables and
charts in the browser.

The dashboard is a read-mostly inspection surface for a benchmark whose identity
is determinism and reproducibility (DG-KVMRSS0C7T4M). That context weights the
trade-off heavily toward keeping the server as the source of truth.

## Decision

Use **progressive enhancement**, not full client-side rendering.

- The server stays the source of every rendered artifact: HTML tables and
  deterministic SVG charts are produced in Python and remain byte-stable and
  committable.
- Interactivity is added as **dependency-free vanilla JS** (no framework, no CDN)
  layered on already-rendered content, living in the editable template
  `runner/templates/dashboard.html`.
- "Live" updates are server-rendered: a `GET /api/fragment` endpoint returns the
  re-rendered `<main>` body, which the page swaps in place instead of doing a
  hard reload.

No charting library is introduced and `scoring/charts.py` is never duplicated in
JavaScript.

## Consequences

### Positive

- The reproducible, offline static `index.html` stays valid; charts remain in the
  file. Sort/filter/toggle work even in that static snapshot (pure DOM).
- One source of truth: cost math, the rac-vs-naive_rag verdict, KPIs, and charts
  stay in Python, shared with `scripts/report.py`.
- No new toolchain: rendering stays covered by hermetic `pytest`; no Node/jsdom.
- Determinism is preserved — server-rendered SVG is diffable and committable.

### Negative

- Each data refresh is a server round-trip (`/api/fragment`), not instant client
  state.
- Rich client-only state (multi-select, undo) is out of reach without server sync.

### Risks

- **Server-render cost** if the dataset grows large. Mitigation: the data volume
  is small (tens of scenarios); paginate or window later if needed.
- **Mid-run curve staleness.** The crossover dataset is written only at run *end*,
  so during a run only the progress bar moves; the fragment refresh gives a true
  update on completion and on demand. Captured as a roadmap risk.

## Status

Accepted

## Category

Architecture

## Alternatives Considered

- **Full client-side rendering (JSON API + JS renders tables/charts).** Rejected:
  it loses the deterministic, committable artifact; needs either a charting
  dependency (CDN/vendoring, against the offline/no-dep ethos) or a
  re-implementation of `scoring/charts.py` in JS (two sources of truth); and adds
  a JavaScript test toolchain to a Python project.
- **A browser charting library (Chart.js/d3) for the curves.** Rejected: a CDN or
  vendored dependency and non-deterministic output, both against the repo ethos.

## Related Decisions

- DG-KVMRSS0C7T4M

## Related Roadmaps

- DG-KVMS7CM76GJK
