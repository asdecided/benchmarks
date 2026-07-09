"""Render the benchmark dashboard as one self-contained HTML page.

Same intent as memorybench's web UI — inspect runs, scenarios, and failures —
with no static-asset or frontend build step: the whole page (CSS + SVG charts +
native <details> drill-down + CSS-only tabs) is one string, dependency-free and
offline, in the spirit of the repo's pure-SVG charts.

This module is the pure renderer (`build_dashboard`). It is served live by
`runner.ui` (the `ui` CLI command) and written to a static file by
`scripts/dashboard.py`. The live cost-vs-N curve is read from the dataset's
recorded token means; the static generator can additionally compute it offline.
"""

from __future__ import annotations

import html
import os
from pathlib import Path

from scoring.charts import grouped_bar_chart, line_chart
from scoring.cost import cost_by_arm, dollars

_DEFAULT_TEMPLATE = Path(__file__).resolve().parent / "templates" / "dashboard.html"


def load_template(template: str | Path | None = None) -> str:
    """The editable HTML shell. Resolution order: explicit `template` arg, then
    the DG_UI_TEMPLATE env var, then the packaged default. The returned text
    must contain the <!--CHIPS--> and <!--BODY--> placeholders."""
    path = Path(template or os.environ.get("DG_UI_TEMPLATE") or _DEFAULT_TEMPLATE)
    text = path.read_text(encoding="utf-8")
    for token in ("<!--CHIPS-->", "<!--BODY-->"):
        if token not in text:
            raise ValueError(f"dashboard template {path} is missing the {token} placeholder")
    return text


def curve_from_dataset(dataset) -> dict | None:
    """Build {arm: {N: mean_input_tokens}} from a crossover dataset's recorded
    per-point token means — the fast, no-recompute cost curve the live UI uses.
    Prefers measured input_tokens_mean, falls back to the token estimate. Returns
    None when the dataset carries no token data (older datasets)."""
    if not dataset:
        return None
    out: dict[str, dict[int, float]] = {}
    for arm, pts in dataset["arms"].items():
        series = {}
        for p in pts:
            tok = p.get("input_tokens_mean", p.get("token_estimate_mean"))
            if tok:
                series[p["N"]] = tok
        if series:
            out[arm] = series
    return out or None

_ARM_DESC = {
    "context_dump": "pastes the entire corpus into the prompt (no-retrieval ceiling)",
    "naive_rag": "embeds the corpus, retrieves top-k chunks (classic RAG)",
    "no_grounding": "supplies nothing — parametric memory only (control)",
    "rac": "typed, supersession-aware grounding assembled by the rac CLI",
    "memory_provider": "pluggable external memory provider (stub)",
}



def _esc(s):
    return html.escape(str(s))


def _f(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


def _has_partial_coverage(d):
    """An arm has partial coverage if any cell didn't score — a generic error
    OR a context-window-exceeded cell both leave n_runs short of n_total."""
    return bool(d.get("n_errors", 0) or d.get("n_context_exceeded", 0))


def _coverage_cell(d):
    """`n_runs/n_total` with an asterisk when the arm has error or context-
    window-exceeded cells — a partial-coverage rate must never read
    identically to a full one."""
    n_total = d.get("n_total", d.get("n_runs", 0))
    mark = "*" if _has_partial_coverage(d) else ""
    return f"{d.get('n_runs', 0)}/{n_total}{mark}"


def _metric_table(run):
    m = run["metrics_by_arm"]
    any_errors = any(_has_partial_coverage(d) for d in m.values())
    rows = ['<table id=leaderboard class=sortable><thead><tr>'
            '<th class=sort>arm</th><th class=sort>adherence</th><th class=sort>stale</th>'
            '<th class=sort>false-permit</th><th class=sort>false-prohibit</th>'
            '<th class=sort>gov-recall</th><th class=sort>coverage</th></tr></thead><tbody>']
    for a in sorted(m, key=lambda a: m[a]["adherence_rate"], reverse=True):
        d = m[a]
        rows.append(
            f'<tr data-arm="{_esc(a)}"><td><code>{_esc(a)}</code></td><td>{_f(d["adherence_rate"])}</td>'
            f"<td>{_f(d['stale_decision_rate'])}</td><td>{_f(d['false_permit_rate'])}</td>"
            f"<td>{_f(d['false_prohibit_rate'])}</td><td>{_f(d.get('governing_recall_rate'))}</td>"
            f"<td>{_esc(_coverage_cell(d))}</td></tr>"
        )
    table = "".join(rows) + "</tbody></table>"
    if any_errors:
        table += (
            '<p class=note>* partial coverage — this arm has error and/or '
            "context-window-exceeded cells; its rate is averaged over "
            "completed cells only, not the full scenario set.</p>"
        )
    return table


def _curve_incomplete(p):
    """A curve cell whose scenarios didn't all complete — a generic error OR a
    context-window-exceeded cell. `.get` keeps old datasets readable."""
    return bool(p.get("error_count", 0) or p.get("context_window_exceeded_count", 0))


def _curve_cell(p, field, flag_coverage=False):
    """A curve table cell: `mean` (single seed) or `mean ±half` (multi-seed CI).
    A coverage-flagged adherence cell with incomplete coverage gets a `*`."""
    v = p.get(field)
    if v is None:
        return "n/a"
    ci = p.get(f"{field}_ci")
    if ci and p.get("n_seeds", 1) > 1:
        body = f"{_f(v)} ±{_f((ci[1] - ci[0]) / 2)}"
    else:
        body = _f(v)
    if flag_coverage and _curve_incomplete(p):
        body += "*"
    return body


def _curve_table(dataset, field):
    arms, ns = dataset["arms"], dataset["ns"]
    flag = field == "adherence_rate"
    head = "".join(f"<th>N={n}</th>" for n in ns)
    rows = [f"<table><thead><tr><th>arm</th>{head}</tr></thead><tbody>"]
    incomplete = False
    for a in arms:
        pts = {p["N"]: p for p in arms[a]}
        for n in ns:
            if flag and _curve_incomplete(pts.get(n, {})):
                incomplete = True
        cells = "".join(
            f"<td>{_curve_cell(pts.get(n, {}), field, flag_coverage=flag)}</td>"
            for n in ns)
        rows.append(f"<tr><td><code>{_esc(a)}</code></td>{cells}</tr>")
    table = "".join(rows) + "</tbody></table>"
    if incomplete:
        table += ("<p class=note>* partial coverage — some scenarios at this N "
                  "errored or exceeded the context window; the rate is over "
                  "completed cells only.</p>")
    return table


def _bands(dataset, field, arms=None):
    """{arm: [(N, lo, hi)]} from per-point `<field>_ci` for chart confidence
    bands. None when the dataset is single-seed (no CI)."""
    out = {}
    for a, pts in dataset["arms"].items():
        if arms is not None and a not in arms:
            continue
        band = [(p["N"], p[f"{field}_ci"][0], p[f"{field}_ci"][1])
                for p in pts if p.get(f"{field}_ci") and p.get("n_seeds", 1) > 1]
        if band:
            out[a] = band
    return out or None


def _cost_section(run, cost_curve, model):
    by = cost_by_arm(run["runs"]); bt = cost_by_arm(run["runs"], batch=True)
    exact = all(v["exact"] for v in by.values())
    rows = ["<table><thead><tr><th>arm</th><th>mean input tok</th><th>mean output tok</th>"
            "<th>$/call (std)</th><th>$/call (batch)</th></tr></thead><tbody>"]
    for a in sorted(by, key=lambda a: by[a]["input_tokens_mean"], reverse=True):
        d, b = by[a], bt[a]
        rows.append(
            f"<tr><td><code>{_esc(a)}</code></td><td>{d['input_tokens_mean']:,.0f}</td>"
            f"<td>{d['output_tokens_mean']:,.0f}</td><td>${d['usd_mean']:.4f}</td>"
            f"<td>${b['usd_mean']:.4f}</td></tr>")
    out = [f"<p class=note>Base-N cost from {'measured API usage' if exact else 'deterministic token estimate'}. "
           "Std and Batch-API (−50%) at the pinned model's rates.</p>",
           "".join(rows) + "</tbody></table>"]
    if cost_curve:
        svg = line_chart("Token cost vs corpus size (input tokens)",
                         {a: [(n, cost_curve[a][n]) for n in sorted(cost_curve[a])] for a in cost_curve},
                         x_label="Corpus size N (log)", y_label="mean input tokens (log)",
                         x_log=True, y_log=True)
        big = max(next(iter(cost_curve.values())))
        crows = ["<table><thead><tr><th>arm</th>" +
                 "".join(f"<th>N={n}</th>" for n in sorted(next(iter(cost_curve.values())))) +
                 "<th>$/call @maxN (batch)</th></tr></thead><tbody>"]
        for a in cost_curve:
            cells = "".join(f"<td>{cost_curve[a][n]:,.0f}</td>" for n in sorted(cost_curve[a]))
            try:
                usd = dollars(int(cost_curve[a][big]), 0, model, batch=True)
                cells += f"<td>${usd:.4f}</td>"
            except KeyError:
                cells += "<td>n/a</td>"
            crows.append(f"<tr><td><code>{_esc(a)}</code></td>{cells}</tr>")
        out += [f"<div class=chart>{svg}</div>", "".join(crows) + "</tbody></table>"]
    return "".join(out)


def _scenarios_section(run):
    runs = run["runs"]
    arms = sorted({r["arm"] for r in runs})
    scen = sorted({r["scenario_id"] for r in runs})
    by = {(r["arm"], r["scenario_id"]): r for r in runs}

    # controls (progressive enhancement; inert without JS / in static snapshots)
    controls = (
        '<div class=controls>'
        '<input id=scen-search type=search placeholder="filter scenarios…" '
        'oninput="filterScenarios(this.value)" aria-label="filter scenarios">'
        '<label><input id=scen-fail type=checkbox onchange="toggleFailures(this.checked)"> '
        'failures only</label></div>'
    )
    # matrix
    head = "".join(f"<th class=sort>{_esc(a)}</th>" for a in arms)
    mrows = [f"<table id=scenario-matrix class=sortable><thead><tr><th class=sort>scenario</th>{head}</tr></thead><tbody>"]
    for s in scen:
        cells = ""
        any_miss = False
        for a in arms:
            r = by.get((a, s))
            if r is None:
                cells += "<td>–</td>"; continue
            ok = r["score"]["adherent"]
            any_miss = any_miss or not ok
            cells += f'<td class="{ "ok" if ok else "bad"}">{"✓" if ok else "✗"}</td>'
        mrows.append(f'<tr data-scenario="{_esc(s)}" data-fail="{int(any_miss)}"><td>{_esc(s)}</td>{cells}</tr>')
    matrix = controls + "".join(mrows) + "</tbody></table>"

    # per-scenario drill-down (inspect failures) via native <details>
    drill = ["<h2>Drill-down</h2>",
             "<p class=note>Each scenario: what every arm proposed, what it cited, and "
             "whether its grounding actually contained the governing decision.</p>"]
    for s in scen:
        any_miss = any(not by[(a, s)]["score"]["adherent"] for a in arms if (a, s) in by)
        rows = ["<table><thead><tr><th>arm</th><th>adherent</th><th>stance</th>"
                "<th>cited</th><th>gov retrieved</th><th>summary</th></tr></thead><tbody>"]
        for a in arms:
            r = by.get((a, s))
            if r is None:
                continue
            sc = r["score"]; pc = r["proposed_change"]; rt = r["retrieval"]
            stance = ("prohibit" if pc["asserts_prohibition"] else
                      "permit" if pc["asserts_permission"] else "—")
            gov = rt["governing_decision_retrieved"]
            govs = "–" if gov is None else ("yes" if gov else "no")
            cls = "ok" if sc["adherent"] else "bad"
            rows.append(
                f"<tr><td><code>{_esc(a)}</code></td>"
                f'<td class="{cls}">{"✓" if sc["adherent"] else "✗"}</td>'
                f"<td>{_esc(stance)}</td><td>{_esc(', '.join(pc['cites_decisions']) or '—')}</td>"
                f"<td>{govs}</td><td>{_esc(pc['summary'][:120])}</td></tr>")
        mark = " ⚠️" if any_miss else ""
        drill.append(f'<details data-scenario="{_esc(s)}" data-fail="{int(any_miss)}">'
                     f"<summary>{_esc(s)}{mark}</summary>"
                     + "".join(rows) + "</tbody></table></details>")
    return matrix + "".join(drill)


def _run_tab(paid: bool) -> str:
    if paid:
        real = (
            "<h2>Real run (paid)</h2>"
            "<p class=note>Pinned Opus 4.8 + Voyage. Estimate first, then tick the box to confirm.</p>"
            "<div class=runform>"
            "<label>Command <select id=r-cmd>"
            "<option value=compare>compare (base-N headline)</option>"
            "<option value=crossover>crossover (adherence-vs-N)</option></select></label> "
            "<label>N (crossover) <input id=r-ns value='10,50' size=10></label> "
            "<label><input type=checkbox id=r-batch> Batch API (−50%)</label> "
            "<button onclick=estimate()>Estimate £</button> <span id=r-est class=note></span>"
            "<br><label><input type=checkbox id=r-confirm> I confirm the estimated spend</label> "
            "<button onclick=runReal()>Run real</button></div>"
        )
    else:
        real = ("<h2>Real run (paid)</h2><p class=note>Disabled. Restart the server with "
                "<code>DG_UI_ALLOW_PAID=1</code> (and <code>ANTHROPIC_API_KEY</code>) to enable; "
                "you'll still have to estimate and tick a confirmation before any spend.</p>")
    return (
        "<section class=tab id=s7><h2>Run the benchmark</h2>"
        "<p class=note>Triggers the CLI on the server; the page refreshes when the run finishes.</p>"
        "<button onclick=runOffline()>Run offline (free)</button> "
        "<button onclick=refreshMain()>↻ Refresh data</button> "
        "<span class=note>offline-stub + local-hash — zero spend</span>"
        "<div id=run-status style='margin-top:14px'></div>"
        + real + "</section>"
    )


def render_main(run, dataset, cost_curve=None, *, live=False, paid_enabled=False):
    """The tab sections — the inner of <main>. Shared by build_dashboard and the
    live /api/fragment endpoint, so an in-place refresh re-renders server-side
    (single source of truth; SVG stays Python-generated)."""
    model = run["runs"][0]["answering_model"]["version"] if run["runs"] else "?"
    m = run["metrics_by_arm"]
    n_scen = len({r["scenario_id"] for r in run["runs"]})
    # Fast cost-vs-N for the live UI: read the dataset's recorded token means when
    # no precomputed curve was passed (the static generator passes the offline one).
    if cost_curve is None:
        cost_curve = curve_from_dataset(dataset)

    # KPIs
    grounded = [a for a in m if a != "no_grounding"]
    best_adh = max((m[a]["adherence_rate"] for a in grounded), default=0)
    none_adh = m.get("no_grounding", {}).get("adherence_rate", 0)
    kpis = [
        ("KPI grounded vs none", f"{best_adh:.2f} vs {none_adh:.2f}", "adherence: grounded vs no-grounding"),
        ("scenarios", str(n_scen), "real pinned decisions (PEP/RFC/W3C)"),
    ]
    if cost_curve and "rac" in cost_curve and "context_dump" in cost_curve:
        big = max(cost_curve["rac"])
        ratio = cost_curve["context_dump"][big] / max(cost_curve["rac"][big], 1)
        kpis.append(("cost", f"{ratio:.0f}×", f"context_dump vs rac tokens @N={big}"))
    kpi_html = "".join(f'<div class=kpi><div class=n>{_esc(v)}</div><div class=l>{_esc(l)}</div></div>'
                       for _, v, l in kpis)

    # tab section bodies
    secs = []
    # 0 Overview
    secs.append(
        f'<section class=tab id=s0><div class=kpis>{kpi_html}</div>'
        "<h2>What this measures</h2><p class=sub>One held-constant answering model behind one "
        "held-constant scaffold; the arms differ <b>only</b> in the grounding they supply. "
        "Scoring is deterministic and structural — no embeddings, no LLM judge.</p>"
        "<h2>Arms</h2><ul>" +
        "".join(f"<li><code>{_esc(a)}</code> — {_esc(_ARM_DESC.get(a,''))}</li>"
                for a in sorted(m)) + "</ul></section>")
    # 1 Leaderboard
    bar = grouped_bar_chart("Base-N decision quality by arm", sorted(m, key=lambda a: m[a]["adherence_rate"], reverse=True),
                            {"adherence": {a: m[a]["adherence_rate"] for a in m},
                             "gov-recall": {a: (m[a].get("governing_recall_rate") or 0) for a in m},
                             "false-permit": {a: m[a]["false_permit_rate"] for a in m}},
                            y_label="rate")
    secs.append(f'<section class=tab id=s1><h2>Leaderboard (base corpus size)</h2>'
                f'<div class=chart>{bar}</div>{_metric_table(run)}</section>')
    # 2 Curves
    if dataset:
        a_svg = line_chart("Decision adherence vs corpus size",
                           {a: [(p["N"], p["adherence_rate"]) for p in dataset["arms"][a]
                                if p.get("adherence_rate") is not None] for a in dataset["arms"]},
                           x_label="Corpus size N (log)", y_label="adherence", x_log=True, y_max=1.05,
                           bands=_bands(dataset, "adherence_rate"))
        r_svg = line_chart("Governing-decision recall vs corpus size",
                           {a: [(p["N"], p["governing_recall"] or 0) for p in dataset["arms"][a]] for a in dataset["arms"]},
                           x_label="Corpus size N (log)", y_label="recall", x_log=True, y_max=1.05,
                           bands=_bands(dataset, "governing_recall"))
        secs.append(f'<section class=tab id=s2><h2>Adherence vs N</h2><div class=chart>{a_svg}</div>'
                    f'{_curve_table(dataset, "adherence_rate")}'
                    f'<h2>Governing-decision recall vs N</h2><div class=chart>{r_svg}</div>'
                    f'{_curve_table(dataset, "governing_recall")}</section>')
    else:
        secs.append('<section class=tab id=s2><p class=note>No crossover dataset supplied — '
                    'run <code>make real-crossover</code> to populate the vs-N curves.</p></section>')
    # 3 Cost
    secs.append(f'<section class=tab id=s3><h2>Token cost</h2>{_cost_section(run, cost_curve, model)}</section>')
    # 4 rac vs naive_rag
    if dataset and "rac" in dataset["arms"] and "naive_rag" in dataset["arms"]:
        hh = line_chart("rac vs naive RAG — adherence vs N",
                        {a: [(p["N"], p["adherence_rate"]) for p in dataset["arms"][a]
                             if p.get("adherence_rate") is not None] for a in ("rac", "naive_rag")},
                        x_label="Corpus size N (log)", y_label="adherence", x_log=True, y_max=1.05,
                        bands=_bands(dataset, "adherence_rate", arms=("rac", "naive_rag")))
        ns = dataset["ns"]; base, top = ns[0], ns[-1]
        paired = (dataset.get("paired") or {}).get("rac_vs_naive_rag")
        if paired:
            # Multi-seed: the falsifier is the paired difference's CI at the top N.
            e = paired[-1]
            lo, hi = e["diff_ci"]
            if lo > 1e-9:
                v = (f"At N={e['N']} rac leads naive_rag by {e['diff_mean']:+.2f} "
                     f"(95% CI [{lo:+.2f}, {hi:+.2f}], {e['n']} seeds) — thesis supported here.")
            elif hi < -1e-9:
                v = (f"At N={e['N']} naive_rag leads rac ({e['diff_mean']:+.2f}, "
                     f"95% CI [{lo:+.2f}, {hi:+.2f}]) — thesis not supported.")
            else:
                v = (f"At N={e['N']} the rac−naive_rag difference is {e['diff_mean']:+.2f} "
                     f"(95% CI [{lo:+.2f}, {hi:+.2f}] includes 0) — not statistically "
                     f"separable; thesis not supported by this run.")
        else:
            ra = {p["N"]: p["adherence_rate"] for p in dataset["arms"]["rac"]}
            na = {p["N"]: p["adherence_rate"] for p in dataset["arms"]["naive_rag"]}
            ra_top, na_top = ra.get(top), na.get(top)
            if ra_top is None or na_top is None:
                v = (f"At N={top}, no adherence rate is available for at least one arm — "
                     "every cell either hit the answering model's context window or "
                     "failed (see context_window_exceeded_count / error_count); the "
                     "thesis is not evaluable at this N.")
            elif na_top < ra_top - 1e-9:
                v = f"rac holds adherence as the corpus grows where naive_rag decays (N={top}: rac {_f(ra_top)} vs naive_rag {_f(na_top)})."
            elif abs(na_top - ra_top) <= 1e-9:
                v = f"At N={top} the two tie ({_f(ra_top)}); naive RAG does not measurably degrade here — thesis not supported by this run."
            else:
                v = f"naive_rag leads rac at N={top} ({_f(na_top)} vs {_f(ra_top)}) — thesis not supported by this run."
        secs.append(f'<section class=tab id=s4><h2>rac vs naive RAG</h2><div class=chart>{hh}</div>'
                    f'<div class=verdict>{_esc(v)}</div></section>')
    else:
        secs.append('<section class=tab id=s4><p class=note>Needs both rac and naive_rag in a crossover dataset.</p></section>')
    # 5 Scenarios
    secs.append(f'<section class=tab id=s5><h2>Scenarios &amp; failures</h2>{_scenarios_section(run)}</section>')
    # 6 Reproduce
    secs.append('<section class=tab id=s6><h2>Reproduce</h2><pre>'
                'make real-crossover   # headline + adherence-vs-N over the real pool\n'
                'make real-batch       # via the Batch API (~50% cost)\n\n'
                'make ui               # serve this dashboard live at 127.0.0.1:8099\n'
                'decisiongrounding ui --port 8099 --results results/published\n\n'
                '# static snapshot (with the offline cost-vs-N curve):\n'
                'python -m scripts.dashboard --run &lt;run.json&gt; \\\n'
                '    --crossover &lt;dataset.json&gt; --cost-curve --out results/published/index.html'
                '</pre></section>')

    # 7 Run (live UI only — needs the server's endpoints)
    if live:
        secs.append(_run_tab(paid_enabled))
    return "".join(secs)


# Tab labels, in section order (s0..s6, +s7 Run when live). Kept beside the
# renderer so the nav and the sections stay in lockstep.
_TABS = ["Overview", "Leaderboard", "Curves", "Cost", "rac vs RAG", "Scenarios", "Reproduce"]


def build_dashboard(run, dataset, cost_curve=None, *, live=False, paid_enabled=False, template=None):
    model = run["runs"][0]["answering_model"]["version"] if run["runs"] else "?"
    emb = next((r["embedder"]["name"] for r in run["runs"] if r.get("embedder")), "n/a")
    n_scen = len({r["scenario_id"] for r in run["runs"]})
    sections = render_main(run, dataset, cost_curve, live=live, paid_enabled=paid_enabled)

    tabs = _TABS + (["Run"] if live else [])
    radios = "".join(f'<input class=tabsel type=radio name=tab id=t{i} {"checked" if i==0 else ""}>'
                     for i in range(len(tabs)))
    nav = "<nav>" + "".join(f'<label for=t{i}>{_esc(t)}</label>' for i, t in enumerate(tabs)) + "</nav>"
    chips = "".join(f'<span class=chip>{_esc(c)}</span>' for c in
                    [f"answering: {model}", f"embedder: {emb}", f"{n_scen} scenarios",
                     f"distractors: {dataset.get('pool_size','—')} real" if dataset else "no crossover yet"])
    body = radios + nav + "<main>" + sections + "</main>"
    # Inject the data-bound parts into the editable HTML shell (the .html template).
    return load_template(template).replace("<!--CHIPS-->", chips).replace("<!--BODY-->", body)
