---
schema_version: 1
id: DG-KVMS7CM76GJK
type: roadmap
tags: [ui, dashboard, progressive-enhancement]
---
# Dashboard Progressive Enhancement

## Outcomes

- A reviewer can **find and focus** results fast: sort and filter/search the
  leaderboard and scenario tables, and jump to failures, without leaving the page.
- A reviewer can **isolate a comparison**: show/hide individual arms on the
  adherence/recall/cost curves to read a head-to-head cleanly.
- A reviewer **keeps their place** while results change: the dashboard refreshes
  in place (no full reload) on demand and when a run completes.
- All of the above arrives **without a JavaScript framework or CDN** and **without
  losing the reproducible, committable static dashboard** — see DG-KVMS87QZDXJY.

## Initiatives

- **Sortable, filterable tables.** Add `data-*` hooks to the leaderboard and
  scenario tables in `runner/dashboard.py`; add a search box and a "failures
  only" toggle; client-side sort on column headers. Pure DOM, so it also works in
  the static snapshot. Supports outcome 1.
- **Chart arm toggles.** Wrap each line-chart series and legend entry in
  `scoring/charts.py` with `data-arm` groups; click a legend entry to show/hide
  that arm. No re-fetch, no charting dependency. Supports outcome 2.
- **In-place refresh.** Factor the page body into `render_main()` and expose it as
  `GET /api/fragment` in `runner/ui.py`; the page swaps `<main>` instead of
  reloading, on a Refresh control and on run completion. Supports outcome 3.

## Success Measures

- Clicking a leaderboard/scenario column header sorts it; the search box and
  "failures only" toggle filter rows — and these work in the committed static
  `index.html` offline.
- Clicking a curve legend entry hides/shows that arm's series.
- A completed run updates the dashboard `<main>` in place, preserving the active
  tab, with no full-page reload.
- `python -m pytest -q` stays green; `rac validate` / `rac relationships
  --validate` / `rac review` stay green for the corpus.

## Assumptions

- The dashboard remains a read-mostly inspection surface; vanilla JS is enough.
- Charts and tables stay server-rendered (the determinism the benchmark depends
  on); the client only enhances already-rendered content.

## Risks

- **Dataset writes at run end.** The crossover dataset is produced only when a run
  finishes, so mid-run the curves cannot update — only the progress bar moves.
  Mitigation: the fragment refresh updates on completion and on demand; this is an
  accepted bound, recorded in DG-KVMS87QZDXJY.
- **Static-artifact regression.** Changes must stay additive so the committed
  `index.html` keeps rendering and its client-only features (sort/filter/toggle)
  keep working without a server.

## Related Decisions

- DG-KVMS87QZDXJY
- DG-KVMRSS0C7T4M

## Related Designs

- DG-KVMS7SDQFSX5
