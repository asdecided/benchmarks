---
schema_version: 1
id: DG-KVMS7SDQFSX5
type: design
tags: [ui, dashboard, implementation]
---
# Dashboard Progressive Enhancement — Implementation

## Context

The dashboard renderer lives in `runner/dashboard.py` (`build_dashboard` plus
`_metric_table`, `_scenarios_section`, the chart sections). The editable shell —
CSS and the existing run-poll JavaScript — is `runner/templates/dashboard.html`.
Charts are deterministic SVG from `scoring/charts.py`. The live server
(`runner/ui.py`) serves the page and `/api/*` JSON; `scripts/dashboard.py` writes
a static snapshot. This design adds interactivity by progressive enhancement
(DG-KVMS87QZDXJY) — additive markup hooks plus vanilla JS, no framework, no CDN.

## User Need

A reviewer inspecting a run wants to: scan the leaderboard sorted by a metric;
search the scenarios and see only failures; isolate one or two arms on a curve to
read a head-to-head; and, after triggering a run, see results update without
losing their scroll position or active tab.

## Design

### Sortable / filterable tables
- `_metric_table`: add `id=leaderboard`, `data-arm` on each `<tr>`, and a
  `class=sort` marker on sortable `<th>`.
- `_scenarios_section`: add `id=scenario-matrix`, `data-scenario` on matrix rows,
  and `data-scenario` on each drill-down `<details>`. Add a search `<input>` and a
  "failures only" checkbox at the top of the Scenarios tab.
- Template JS (vanilla, in `dashboard.html`): `sortTable(th)` (numeric- and
  text-aware, toggles direction), `filterRows(query)` over the matrix, and a
  failures-only toggle that hides `<details>` lacking the ⚠️ marker. Pure DOM, so
  it also works in the static snapshot.

### Chart arm show/hide
- `scoring/charts.py` `line_chart`: wrap each series' polyline + circles in
  `<g data-arm="{label}">`, and wrap each legend swatch+label in
  `<g class=legend data-arm="{label}" style="cursor:pointer">`.
- Template JS: a click on a legend `g[data-arm]` toggles `display` on the matching
  `g[data-arm]` series within that SVG. No re-fetch, no charting dependency.

### In-place refresh
- Factor the page body (radios + nav + `<main>`… or just the `<main>` sections)
  out of `build_dashboard` into `render_main(run, dataset, *, live, paid_enabled)`.
- Add `GET /api/fragment` to `build_ui_app` returning `render_main(...)` from the
  latest results (server-rendered SVG, reusing `scoring/charts.py`).
- Template JS: a Refresh control and the run-completion handler replace
  `document.querySelector('main').innerHTML` with the fragment (tab radios live
  outside `<main>`, so the active tab is preserved), superseding `location.reload()`.

## Constraints

- **No JS framework or CDN**; deterministic, server-rendered SVG stays the single
  source of truth (DG-KVMS87QZDXJY, DG-KVMRSS0C7T4M).
- **Additive only**: new `data-*`/`id` hooks must not change existing output shape,
  so the committed static `index.html` stays valid.
- **Graceful degradation**: sort/filter/toggle are pure DOM and work offline in the
  static file; only the fragment refresh needs the server (no-ops otherwise).

## Rationale

Reuses the existing renderer, charts, and `/api/*` surface; the hooks are a handful
of attributes and the behaviour is a small vanilla-JS file. It delivers the
interactive wins while preserving determinism and the reproducible artifact, which
a full client-side rewrite would forfeit.

## Alternatives

- **Full client-side rendering** — rejected in DG-KVMS87QZDXJY (loses the
  committable artifact; needs a charting dependency or duplicated chart logic; adds
  a JS test toolchain).
- **Re-fetch and re-render charts client-side from `/api/crossover`** — rejected:
  would duplicate `scoring/charts.py` in JS; the server-rendered `/api/fragment`
  keeps one source of truth.

## Accessibility

- Sortable headers are operable controls (button semantics / keyboard activatable);
  the search box is a labelled `<input>`; the failures-only control is a checkbox.
- The drill-down already uses native `<details>`/`<summary>` (keyboard-accessible).
- Arm toggles are activatable from the keyboard and do not rely on colour alone
  (the row/label text remains).

## Style Guidance

- Reuse the existing CSS variables and classes in `dashboard.html` (`.note`,
  `.chart`, table styles). Add only minimal styles (e.g. a sort caret, legend
  `cursor:pointer`). Keep the look consistent with the current tabs.

## Open Questions

- Should sort/filter and arm-visibility persist across an in-place refresh? Out of
  scope for v1 (refresh resets to the server-rendered defaults); revisit if it
  proves annoying in use.

## Related Roadmaps

- DG-KVMS7CM76GJK

## Related Decisions

- DG-KVMS87QZDXJY
