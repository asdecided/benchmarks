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

from scoring.charts import grouped_bar_chart, line_chart
from scoring.cost import cost_by_arm, dollars


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

_CSS = """
:root{--fg:#1a1a1a;--mut:#666;--line:#e3e3e3;--ok:#2ca02c;--bad:#d62728;--bg:#fff;--card:#fafafa}
*{box-sizing:border-box}
body{font-family:-apple-system,Segoe UI,Roboto,sans-serif;color:var(--fg);margin:0;background:var(--bg);line-height:1.5}
header{padding:28px 32px 18px;border-bottom:1px solid var(--line)}
h1{margin:0 0 6px;font-size:24px}
.sub{color:var(--mut);max-width:760px}
.chips{margin-top:14px;display:flex;flex-wrap:wrap;gap:8px}
.chip{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:4px 12px;font-size:13px}
main{padding:0 32px 48px}
.kpis{display:flex;flex-wrap:wrap;gap:16px;margin:22px 0}
.kpi{flex:1;min-width:180px;background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}
.kpi .n{font-size:26px;font-weight:700}
.kpi .l{color:var(--mut);font-size:13px;margin-top:2px}
nav{display:flex;gap:6px;border-bottom:1px solid var(--line);margin-top:8px;flex-wrap:wrap}
nav label{padding:10px 16px;cursor:pointer;font-size:14px;color:var(--mut);border-bottom:2px solid transparent;margin-bottom:-1px}
nav label:hover{color:var(--fg)}
section.tab{display:none;padding-top:22px}
input.tabsel{position:absolute;left:-9999px}
""" + "".join(
    f"#t{i}:checked~nav label[for=t{i}]{{color:var(--fg);border-bottom-color:var(--fg);font-weight:600}}"
    f"#t{i}:checked~main #s{i}{{display:block}}"
    for i in range(8)
) + """
table{border-collapse:collapse;width:100%;margin:8px 0 18px;font-size:14px}
th,td{border:1px solid var(--line);padding:7px 10px;text-align:right}
th:first-child,td:first-child{text-align:left}
thead th{background:var(--card)}
code{background:var(--card);padding:1px 5px;border-radius:4px;font-size:13px}
pre{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:14px;overflow:auto;font-size:13px}
.ok{color:var(--ok);font-weight:700}.bad{color:var(--bad);font-weight:700}
.chart{margin:10px 0 22px;max-width:760px}
.chart svg{max-width:100%;height:auto;border:1px solid var(--line);border-radius:8px}
details{border:1px solid var(--line);border-radius:8px;margin:6px 0;padding:6px 12px;background:var(--card)}
summary{cursor:pointer;font-weight:600}
details table{margin:10px 0 4px}
.note{color:var(--mut);font-size:13px;margin:6px 0}
.verdict{background:#f0f7f0;border:1px solid #cfe5cf;border-radius:8px;padding:12px 14px;max-width:760px}
h2{font-size:18px;margin:26px 0 6px}
"""


def _esc(s):
    return html.escape(str(s))


def _f(x, nd=2):
    return "n/a" if x is None else f"{x:.{nd}f}"


def _metric_table(run):
    m = run["metrics_by_arm"]
    rows = ["<table><thead><tr><th>arm</th><th>adherence</th><th>stale</th>"
            "<th>false-permit</th><th>false-prohibit</th><th>gov-recall</th></tr></thead><tbody>"]
    for a in sorted(m, key=lambda a: m[a]["adherence_rate"], reverse=True):
        d = m[a]
        rows.append(
            f"<tr><td><code>{_esc(a)}</code></td><td>{_f(d['adherence_rate'])}</td>"
            f"<td>{_f(d['stale_decision_rate'])}</td><td>{_f(d['false_permit_rate'])}</td>"
            f"<td>{_f(d['false_prohibit_rate'])}</td><td>{_f(d.get('governing_recall_rate'))}</td></tr>"
        )
    return "".join(rows) + "</tbody></table>"


def _curve_table(dataset, field):
    arms, ns = dataset["arms"], dataset["ns"]
    head = "".join(f"<th>N={n}</th>" for n in ns)
    rows = [f"<table><thead><tr><th>arm</th>{head}</tr></thead><tbody>"]
    for a in arms:
        pts = {p["N"]: p for p in arms[a]}
        cells = "".join(f"<td>{_f(pts.get(n, {}).get(field))}</td>" for n in ns)
        rows.append(f"<tr><td><code>{_esc(a)}</code></td>{cells}</tr>")
    return "".join(rows) + "</tbody></table>"


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

    # matrix
    head = "".join(f"<th>{_esc(a)}</th>" for a in arms)
    mrows = [f"<table><thead><tr><th>scenario</th>{head}</tr></thead><tbody>"]
    for s in scen:
        cells = ""
        for a in arms:
            r = by.get((a, s))
            if r is None:
                cells += "<td>–</td>"; continue
            ok = r["score"]["adherent"]
            cells += f'<td class="{ "ok" if ok else "bad"}">{"✓" if ok else "✗"}</td>'
        mrows.append(f"<tr><td>{_esc(s)}</td>{cells}</tr>")
    matrix = "".join(mrows) + "</tbody></table>"

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
        drill.append(f"<details><summary>{_esc(s)}{mark}</summary>"
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
        "<span class=note>offline-stub + local-hash — zero spend</span>"
        "<div id=run-status style='margin-top:14px'></div>"
        + real + "</section>"
    )


_RUN_JS = """<script>
async function jget(u){const r=await fetch(u);return r.json()}
async function jpost(u,b){const r=await fetch(u,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(b)});return {ok:r.ok,data:await r.json()}}
let poll_stop=false;
function esc(t){return (t||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}
function renderStatus(s){
  const el=document.getElementById('run-status'); if(!el)return;
  if(!s||s.state==='idle'){el.innerHTML='<span class=note>idle — no run yet</span>';return;}
  const p=s.progress||{}; let bar='';
  if(p.total){const pct=p.pct||0; bar=`<div style="background:#eee;border-radius:6px;height:14px;max-width:420px;overflow:hidden"><div style="width:${pct}%;background:#2ca02c;height:14px"></div></div><div class=note>${p.done}/${p.total} cells (${pct}%)</div>`;}
  const tail=s.log_tail?`<pre>${esc(s.log_tail)}</pre>`:'';
  el.innerHTML=`<b>${esc(s.state)}</b> &middot; ${esc(s.command||'')} ${esc(s.mode||'')}${bar}${tail}`;
  if(s.state==='done'){el.innerHTML+='<div class=note>done — reloading…</div>';poll_stop=true;setTimeout(()=>location.reload(),1500);}
  if(s.state==='error'){el.innerHTML+='<div class=bad>run failed — see log above</div>';poll_stop=true;}
}
async function poll(){if(poll_stop)return;try{renderStatus(await jget('/api/run/status'))}catch(e){}}
setInterval(poll,2000); poll();
async function runOffline(){poll_stop=false; const r=await jpost('/api/run/start',{mode:'offline',command:'compare'}); if(!r.ok)alert(r.data.error||'failed'); else renderStatus(r.data);}
function cfg(){return {command:document.getElementById('r-cmd').value, ns:document.getElementById('r-ns').value.split(',').map(x=>x.trim()).filter(Boolean), batch:document.getElementById('r-batch').checked};}
async function estimate(){const c=cfg(); const q=new URLSearchParams({command:c.command,ns:c.ns.join(','),batch:c.batch}); const e=await jget('/api/run/estimate?'+q); document.getElementById('r-est').textContent=`~£${e.gbp} ($${e.usd}) · ${e.calls} calls · ${e.note}`; return e;}
async function runReal(){if(!document.getElementById('r-confirm').checked){alert('Tick the confirmation box first.');return;} const e=await estimate(); if(!confirm(`Spend ~£${e.gbp} ($${e.usd}) on ${e.calls} real API calls?`))return; poll_stop=false; const c=cfg(); const r=await jpost('/api/run/start',{mode:'real',command:c.command,ns:c.ns,batch:c.batch,confirm_usd:e.usd}); if(!r.ok)alert(r.data.error||'failed'); else renderStatus(r.data);}
</script>"""


def build_dashboard(run, dataset, cost_curve=None, *, live=False, paid_enabled=False):
    model = run["runs"][0]["answering_model"]["version"] if run["runs"] else "?"
    emb = next((r["embedder"]["name"] for r in run["runs"] if r.get("embedder")), "n/a")
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
                           {a: [(p["N"], p["adherence_rate"]) for p in dataset["arms"][a]] for a in dataset["arms"]},
                           x_label="Corpus size N (log)", y_label="adherence", x_log=True, y_max=1.05)
        r_svg = line_chart("Governing-decision recall vs corpus size",
                           {a: [(p["N"], p["governing_recall"] or 0) for p in dataset["arms"][a]] for a in dataset["arms"]},
                           x_label="Corpus size N (log)", y_label="recall", x_log=True, y_max=1.05)
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
                        {a: [(p["N"], p["adherence_rate"]) for p in dataset["arms"][a]] for a in ("rac", "naive_rag")},
                        x_label="Corpus size N (log)", y_label="adherence", x_log=True, y_max=1.05)
        ns = dataset["ns"]; base, top = ns[0], ns[-1]
        ra = {p["N"]: p["adherence_rate"] for p in dataset["arms"]["rac"]}
        na = {p["N"]: p["adherence_rate"] for p in dataset["arms"]["naive_rag"]}
        if na.get(top, 1) < ra.get(top, 0) - 1e-9:
            v = f"rac holds adherence as the corpus grows where naive_rag decays (N={top}: rac {_f(ra.get(top))} vs naive_rag {_f(na.get(top))})."
        elif abs(na.get(top, 0) - ra.get(top, 0)) <= 1e-9:
            v = f"At N={top} the two tie ({_f(ra.get(top))}); naive RAG does not measurably degrade here — thesis not supported by this run."
        else:
            v = f"naive_rag leads rac at N={top} ({_f(na.get(top))} vs {_f(ra.get(top))}) — thesis not supported by this run."
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

    tabs = ["Overview", "Leaderboard", "Curves", "Cost", "rac vs RAG", "Scenarios", "Reproduce"]
    if live:
        tabs.append("Run")
    radios = "".join(f'<input class=tabsel type=radio name=tab id=t{i} {"checked" if i==0 else ""}>'
                     for i in range(len(tabs)))
    nav = "<nav>" + "".join(f'<label for=t{i}>{_esc(t)}</label>' for i, t in enumerate(tabs)) + "</nav>"
    chips = "".join(f'<span class=chip>{_esc(c)}</span>' for c in
                    [f"answering: {model}", f"embedder: {emb}", f"{n_scen} scenarios",
                     f"distractors: {dataset.get('pool_size','—')} real" if dataset else "no crossover yet"])
    return (
        "<!doctype html><html lang=en><head><meta charset=utf-8>"
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<title>Decision Grounding Bench</title><style>" + _CSS + "</style></head><body>"
        "<header><h1>Decision Grounding Bench</h1>"
        "<div class=sub>Does typed, supersession-aware grounding make an agent follow the right "
        "decision better than context-dump or naive RAG — and at what token cost?</div>"
        f"<div class=chips>{chips}</div></header>"
        + radios + nav + "<main>" + "".join(secs) + "</main>"
        + (_RUN_JS if live else "") + "</body></html>"
    )
