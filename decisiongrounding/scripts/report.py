"""Generate the full decision-grounding report (memorybench-style) from a run.

    python -m scripts.report \
        --run results/published/<headline>.json \
        --crossover results/crossover_dataset.json \
        --cost-curve \
        --out results/published/decision-grounding-report.md

Inputs:
  --run        a `compare`/`batch` run JSON (base-N leaderboard + token cost).
  --crossover  a crossover dataset JSON (adherence/recall-vs-N + chart).
  --cost-curve compute a real token-cost-vs-N curve OFFLINE (no API spend):
               grounding assembly is deterministic, so each arm's token size at
               each N is measured by assembling — never answering. Uses the pool
               and ns recorded in the crossover dataset.

The report is data-driven: every number comes from the inputs. The only prose
that is fixed is the methodology/limitations narrative.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scoring.charts import grouped_bar_chart, line_chart  # noqa: E402
from scoring.cost import cost_by_arm, dollars  # noqa: E402
from scoring.stats import paired_significance  # noqa: E402

_ARM_DESC = {
    "context_dump": "pastes the entire corpus into the prompt (the no-retrieval ceiling)",
    "naive_rag": "embeds the corpus and retrieves the top-k chunks (classic RAG)",
    "naive_rag_full": "cosine retrieval, but supplies each top hit's WHOLE artifact (whole-artifact granularity at equal retrieval)",
    "no_grounding": "supplies nothing — the answering model's parametric memory only (control)",
    "rac": "supplies typed, supersession-aware grounding assembled by the rac CLI",
    "rac_snippets": "rac's typed retrieval, but supplies section snippets under naive_rag's token budget (equal-budget typed retrieval)",
    "memory_provider": "a pluggable external memory provider (stub)",
}


def _fmt(x, nd=2):
    if x is None:
        return "n/a"
    return f"{x:.{nd}f}"


def _has_partial_coverage(d: dict) -> bool:
    """An arm has partial coverage if any cell didn't score — a generic error
    OR a context-window-exceeded cell both leave n_runs short of n_total."""
    return bool(d.get("n_errors", 0) or d.get("n_context_exceeded", 0))


def _coverage(d: dict) -> str:
    """`n_runs/n_total`, flagged with an asterisk when the arm has error or
    context-window-exceeded cells — a partial-coverage rate must never read
    identically to a full one. `.get` defaults keep this readable against
    older reports that predate n_errors/n_context_exceeded/n_total."""
    n_total = d.get("n_total", d.get("n_runs", 0))
    return f"{d.get('n_runs', 0)}/{n_total}" + ("*" if _has_partial_coverage(d) else "")


def _leaderboard(run: dict) -> str:
    m = run["metrics_by_arm"]
    rows = ["| arm | adherence | stale | false-permit | false-prohibit | gov-recall | coverage |",
            "|---|--:|--:|--:|--:|--:|--:|"]
    # adherence high to low
    for arm in sorted(m, key=lambda a: m[a]["adherence_rate"], reverse=True):
        d = m[arm]
        rows.append(
            f"| `{arm}` | {_fmt(d['adherence_rate'])} | {_fmt(d['stale_decision_rate'])} | "
            f"{_fmt(d['false_permit_rate'])} | {_fmt(d['false_prohibit_rate'])} | "
            f"{_fmt(d.get('governing_recall_rate'))} | {_coverage(d)} |"
        )
    if any(_has_partial_coverage(d) for d in m.values()):
        rows.append(
            "\n\\* partial coverage — this arm has error and/or context-window-"
            "exceeded cells; its rate is averaged over completed cells only, "
            "not the full scenario set."
        )
    return "\n".join(rows)


def _cost_table(run: dict) -> tuple[str, bool]:
    by = cost_by_arm(run["runs"])
    batch = cost_by_arm(run["runs"], batch=True)
    exact = all(v["exact"] for v in by.values())
    src = "measured API usage" if exact else "deterministic token estimate (~4 chars/token)"
    rows = [
        f"Token cost per answering call at base corpus size, from {src}. "
        "Standard and Batch-API (50% off) dollars at the pinned model's rates.",
        "",
        "| arm | mean input tok | mean output tok | $/call (std) | $/call (batch) | $/100 calls (batch) |",
        "|---|--:|--:|--:|--:|--:|",
    ]
    for arm in sorted(by, key=lambda a: by[a]["input_tokens_mean"], reverse=True):
        d, b = by[arm], batch[arm]
        rows.append(
            f"| `{arm}` | {d['input_tokens_mean']:,.0f} | {d['output_tokens_mean']:,.0f} | "
            f"${d['usd_mean']:.4f} | ${b['usd_mean']:.4f} | ${b['usd_mean']*100:.2f} |"
        )
    return "\n".join(rows), exact


def _curve_incomplete(p: dict) -> bool:
    """A curve cell has incomplete coverage when any of its scenarios failed —
    a generic error OR a context-window-exceeded cell. `.get` keeps this
    readable against datasets that predate error_count/CWE fields."""
    return bool(p.get("error_count", 0) or p.get("context_window_exceeded_count", 0))


def _curve_cell(p: dict, field: str, nd=2, flag_coverage=False) -> str:
    """`mean` (single seed) or `mean ±half` (multi-seed CI). When
    `flag_coverage`, an adherence cell whose scenarios didn't all complete
    gets a trailing `*` — a partial-coverage rate (averaged over completed
    cells only) must never read identically to a full one."""
    v = p.get(field)
    if v is None:
        return _fmt(None, nd)
    ci = p.get(f"{field}_ci")
    if ci and p.get("n_seeds", 1) > 1:
        body = f"{_fmt(v, nd)} ±{_fmt((ci[1] - ci[0]) / 2, nd)}"
    else:
        body = _fmt(v, nd)
    if flag_coverage and _curve_incomplete(p):
        body += "*"
    return body


def _bands(dataset: dict, field: str, arms=None):
    """{arm: [(N, lo, hi)]} from per-point `<field>_ci` for chart confidence
    bands. None when single-seed (no CI)."""
    out = {}
    for a, pts in dataset["arms"].items():
        if arms is not None and a not in arms:
            continue
        band = [(p["N"], p[f"{field}_ci"][0], p[f"{field}_ci"][1])
                for p in pts if p.get(f"{field}_ci") and p.get("n_seeds", 1) > 1]
        if band:
            out[a] = band
    return out or None


def _curve_table(dataset: dict, field: str, label: str, nd=2) -> str:
    arms = list(dataset["arms"])
    ns = dataset["ns"]
    # Only the adherence curve is coverage-flagged: it is the rate that
    # excludes failed cells, so a partial cell must be visibly marked.
    flag = field == "adherence_rate"
    head = "| arm | " + " | ".join(f"N={n}" for n in ns) + " |"
    sep = "|---|" + "--:|" * len(ns)
    rows = [f"{label}", "", head, sep]
    incomplete = False
    for arm in arms:
        pts = {p["N"]: p for p in dataset["arms"][arm]}
        for n in ns:
            if flag and _curve_incomplete(pts.get(n, {})):
                incomplete = True
        cells = " | ".join(
            _curve_cell(pts.get(n, {}), field, nd, flag_coverage=flag) for n in ns)
        rows.append(f"| `{arm}` | {cells} |")
    if incomplete:
        rows.append(
            "\n\\* partial coverage — some scenarios at this N errored or "
            "exceeded the context window; the rate is over completed cells "
            "only (error and context-window cells are excluded, like the "
            "base-N table)."
        )
    return "\n".join(rows)


def _offline_cost_curve(dataset: dict, pool_dir=None, scen_dir=None) -> dict | None:
    """Measure mean grounding tokens per (arm, N) WITHOUT answering calls.
    Reconstructs the same corpora as the crossover and only assembles grounding.
    Free: uses the local-hash embedder (token COUNT of top-k is ~embedder
    independent) and the rac CLI. Returns {arm: {N: mean_tokens}} or None."""
    from scenarios.loader import load_pool, load_scenarios
    from scoring.crossover import DISCRIMINATING, make_real_distractors
    from providers import build_provider, ScriptedAnsweringModel

    pool_dir = pool_dir or dataset.get("pool_dir")
    scen_dir = scen_dir or dataset.get("scenarios_dir")
    if not pool_dir or not scen_dir:
        return None  # no provenance dirs; pass --pool/--scenarios to enable
    pool = load_pool(pool_dir)
    scenarios = [s for s in load_scenarios(scen_dir) if s.scenario_type in DISCRIMINATING]
    arms = list(dataset["arms"])
    ns = dataset["ns"]
    model = ScriptedAnsweringModel(seed=dataset.get("seed", 0))
    out: dict[str, dict[int, float]] = {arm: {} for arm in arms}
    for n in ns:
        for arm in arms:
            sizes = []
            for sc in scenarios:
                pad = max(0, n - len(sc.corpus))
                corpus = list(sc.corpus) + make_real_distractors(pool, pad, sc, dataset.get("seed", 0))
                p = build_provider(arm, model, "local-hash")
                p.prepare(list(corpus))
                p.assemble(sc.task)
                sizes.append(p.grounding.token_estimate)
            out[arm][n] = sum(sizes) / len(sizes) if sizes else 0
    return out


def _cost_curve_table(curve: dict, model: str) -> str:
    ns = sorted({n for arm in curve for n in curve[arm]})
    head = "| arm | " + " | ".join(f"N={n}" for n in ns) + " |"
    sep = "|---|" + "--:|" * len(ns)
    rows = ["Mean grounding tokens placed in context, by corpus size "
            "(input-token cost; measured offline, no answering spend):", "",
            head, sep]
    for arm in curve:
        cells = " | ".join(f"{curve[arm].get(n, 0):,.0f}" for n in ns)
        rows.append(f"| `{arm}` | {cells} |")
    # dollar blow-up at the largest N, batch pricing
    big = max(ns)
    rows += ["", f"At N={big}, per-call input cost (Batch API):", ""]
    rows.append("| arm | $/call |")
    rows.append("|---|--:|")
    for arm in curve:
        try:
            usd = dollars(int(curve[arm][big]), 0, model, batch=True)
            rows.append(f"| `{arm}` | ${usd:.4f} |")
        except KeyError:
            pass
    return "\n".join(rows)


def _fmt_p(p: float) -> str:
    return "<0.0001" if p < 1e-4 else f"{p:.4f}"


def _stats_pair_rows(pairs_block: dict) -> list[str]:
    """Markdown rows for one paired-significance block (per arm pair)."""
    rows = [
        "| pair | n | b | c | McNemar p | risk diff [95% CI] | odds ratio [95% CI] |",
        "|---|--:|--:|--:|--:|--:|--:|",
    ]
    for name, st in pairs_block.items():
        mc, rd, orr = st["mcnemar"], st["risk_difference"], st["odds_ratio"]
        p_txt = _fmt_p(mc["p_value"]) + (" (degenerate)" if mc.get("degenerate") else "")
        or_txt = ("n/a (zero discordant cell)" if orr.get("degenerate")
                  else f"{orr['or']:.2f} [{orr['ci'][0]:.2f}, {orr['ci'][1]:.2f}]")
        rows.append(
            f"| `{name}` | {st['n_pairs']} | {mc['b']} | {mc['c']} | {p_txt} | "
            f"{rd['diff']:+.2f} [{rd['ci'][0]:+.2f}, {rd['ci'][1]:+.2f}] | {or_txt} |"
        )
    return rows


def _stats_section(run: dict, dataset: dict | None) -> list[str]:
    """The pre-registered paired-significance section. Empty when neither the
    run nor the dataset carries a stats block (older artifacts)."""
    parts: list[str] = []
    run_stats = (run.get("stats") or {}).get("adherent") or {}
    if run_stats.get("pairs"):
        parts += ["**Base-N adherence (paired by scenario):**", "",
                  *_stats_pair_rows(run_stats["pairs"]), ""]
    ds_stats = (dataset or {}).get("stats") or {}
    for n in sorted(ds_stats, key=lambda k: int(k)):
        block = ds_stats[n]
        if block.get("pairs"):
            parts += [f"**Crossover N={n} adherence (paired by scenario × seed):**", "",
                      *_stats_pair_rows(block["pairs"]), ""]
    if not parts:
        return []
    intro = [
        "## Paired significance (pre-registered)",
        "",
        "Exact McNemar tests on the discordant pairs, with paired risk differences "
        "and conditional odds ratios, per `spec/analysis-plan-amendment-1.md`. "
        "`b` = first arm adherent where the second is not; `c` = the reverse. "
        "Analysis only — these statistics never gate anything (ADR-066/ADR-097).",
        "",
    ]
    return intro + parts


def _resolution_section(records: list[dict]) -> list[str]:
    """The decision-conditioned resolution co-primary outcome, from gitchameleon
    resolution records (per-(example, arm) upstream-test pass booleans)."""
    by_arm: dict[str, list[dict]] = {}
    for r in records:
        by_arm.setdefault(r["arm"], []).append(r)
    parts = [
        "## Decision-conditioned resolution (co-primary outcome)",
        "",
        "Executable task success on version-conditioned problems, scored by the "
        "upstream test harness (`../gitchameleon/`; we add no scorer). Pass rate "
        "per arm, with the pre-registered paired analysis:",
        "",
        "| arm | n | pass rate |",
        "|---|--:|--:|",
    ]
    for arm in sorted(by_arm):
        rs = by_arm[arm]
        rate = sum(1 for r in rs if r["passed"]) / len(rs)
        parts.append(f"| `{arm}` | {len(rs)} | {rate:.2f} |")
    st = paired_significance(records, outcome="passed")
    if st["pairs"]:
        parts += ["", *_stats_pair_rows(st["pairs"])]
    parts.append("")
    return parts


def _per_scenario_section(dataset: dict) -> list[str]:
    """Per-arm failure attribution across scenarios — surfaces whether one
    scenario dominates an arm's failures (the pilot found 12 of rac's 13
    failures came from a single scenario). A concentrated failure means the
    verdict rests on that scenario's idiosyncrasies, not a general effect.

    `.get`-guarded so datasets predating `per_scenario` render nothing.
    """
    per = dataset.get("per_scenario")
    if not per:
        return []
    parts = ["## Per-scenario failure attribution", ""]
    for arm in per:
        # failures[scenario_id] = (# non-adherent cells, # scored cells)
        failures: dict[str, tuple[int, int]] = {}
        for sid, cells in per[arm].items():
            scored = [c for c in cells if c.get("adherent") is not None]
            miss = sum(1 for c in scored if not c["adherent"])
            if scored:
                failures[sid] = (miss, len(scored))
        total_fail = sum(m for m, _ in failures.values())
        if total_fail == 0:
            parts.append(f"- **`{arm}`** — no failures across scenarios.")
            continue
        ranked = sorted(failures.items(), key=lambda kv: kv[1][0], reverse=True)
        top_sid, (top_fail, _) = ranked[0]
        parts.append(f"**`{arm}`** — {total_fail} failing cell(s) across scenarios:")
        parts.append("")
        parts.append("| scenario | failing cells | scored cells |")
        parts.append("|---|--:|--:|")
        for sid, (miss, scored) in ranked:
            if miss:
                parts.append(f"| `{sid}` | {miss} | {scored} |")
        if top_fail > total_fail / 2:
            parts.append("")
            parts.append(
                f"⚠ **{top_fail} of {total_fail}** of `{arm}`'s failures come from "
                f"a single scenario (`{top_sid}`) — this arm's result rests "
                f"substantively on that scenario, not a broad effect."
            )
        parts.append("")
    return parts


def _head_to_head(dataset: dict, run: dict) -> str:
    """rac vs naive_rag only — the comparison that actually adjudicates the thesis."""
    arms = dataset["arms"]
    if "rac" not in arms or "naive_rag" not in arms:
        return "_(rac vs naive_rag head-to-head needs both arms in the crossover.)_"
    ns = dataset["ns"]

    def series(arm, field):
        return {p["N"]: p.get(field) for p in arms[arm]}

    rac_a, rag_a = series("rac", "adherence_rate"), series("naive_rag", "adherence_rate")
    rac_r, rag_r = series("rac", "governing_recall"), series("naive_rag", "governing_recall")
    base, top = ns[0], ns[-1]

    def delta(s):
        a, b = s.get(base), s.get(top)
        return None if a is None or b is None else b - a

    rac_da, rag_da = delta(rac_a), delta(rag_a)
    rac_dr, rag_dr = delta(rac_r), delta(rag_r)

    lines = [
        f"Both arms retrieve from the same {dataset.get('pool_size','?')}-distractor pool and feed "
        "the same answering model; they differ only in *how* they select grounding.",
        "",
        _curve_table({"arms": {"rac": arms["rac"], "naive_rag": arms["naive_rag"]}, "ns": ns},
                     "adherence_rate", "**Adherence vs N**"),
        "",
        _curve_table({"arms": {"rac": arms["rac"], "naive_rag": arms["naive_rag"]}, "ns": ns},
                     "governing_recall", "**Governing-decision recall vs N**"),
        "",
        f"**From N={base} to N={top}:**",
        f"- rac adherence Δ {_fmt(rac_da, 2)}, recall Δ {_fmt(rac_dr, 2)}",
        f"- naive_rag adherence Δ {_fmt(rag_da, 2)}, recall Δ {_fmt(rag_dr, 2)}",
        "",
    ]
    # Multi-seed: the falsifier is the paired difference's CI at the top N.
    paired = (dataset.get("paired") or {}).get("rac_vs_naive_rag")
    if paired:
        e = paired[-1]
        lo, hi = e["diff_ci"]
        if lo > 1e-9:
            verdict = (
                f"**rac leads naive_rag at N={e['N']}** by {e['diff_mean']:+.2f} "
                f"(paired 95% CI [{lo:+.2f}, {hi:+.2f}] over {e['n']} seeds) — the thesis "
                "is supported here, with the difference statistically separable from zero."
            )
        elif hi < -1e-9:
            verdict = (
                f"**naive_rag leads rac at N={e['N']}** ({e['diff_mean']:+.2f}, paired 95% "
                f"CI [{lo:+.2f}, {hi:+.2f}]) — the thesis is not supported; reported as-is."
            )
        else:
            verdict = (
                f"**At N={e['N']} the paired rac−naive_rag difference is {e['diff_mean']:+.2f} "
                f"(95% CI [{lo:+.2f}, {hi:+.2f}] includes 0)** — not statistically separable; "
                "the thesis is not supported by this run."
            )
        lines.append(verdict)
        mc_line = _mcnemar_line(dataset, top)
        if mc_line:
            lines += ["", mc_line]
        return "\n".join(lines)
    # auto verdict — strictly from the numbers (single seed)
    if rac_da is not None and rag_da is not None:
        if rag_a.get(top, 1) < rac_a.get(top, 0) - 1e-9:
            verdict = (
                f"**rac holds adherence as the corpus grows where naive_rag decays** "
                f"(N={top}: rac {_fmt(rac_a.get(top))} vs naive_rag {_fmt(rag_a.get(top))}). "
                "The recall rows show why: as the governing decision is buried among "
                "distractors, embedding retrieval stops surfacing it, while typed "
                "supersession-aware assembly still resolves it."
            )
        elif abs(rag_a.get(top, 0) - rac_a.get(top, 0)) <= 1e-9:
            verdict = (
                f"**At N={top} the two arms tie** ({_fmt(rac_a.get(top))}). On this pool "
                "and these scenarios, naive RAG does not measurably degrade relative to "
                "rac — the thesis is not supported by this run, and the report says so."
            )
        else:
            verdict = (
                f"**naive_rag leads rac at N={top}** "
                f"({_fmt(rag_a.get(top))} vs {_fmt(rac_a.get(top))}). The thesis is not "
                "supported by this run; reported as-is."
            )
        lines.append(verdict)
        mc_line = _mcnemar_line(dataset, top)
        if mc_line:
            lines += ["", mc_line]
    return "\n".join(lines)


def _mcnemar_line(dataset: dict, top) -> str | None:
    """The pre-registered confirmatory sentence for rac vs naive_rag at the top
    N, when the dataset carries per-cell stats."""
    ds_stats = dataset.get("stats") or {}
    block = ds_stats.get(top) or ds_stats.get(str(top)) or {}
    st = (block.get("pairs") or {}).get("rac_vs_naive_rag")
    if not st:
        return None
    mc = st["mcnemar"]
    if mc.get("degenerate"):
        return (f"Pre-registered confirmatory test at N={top}: exact McNemar is "
                "degenerate (the arms never disagreed on any paired cell) — "
                "no discordant evidence either way.")
    return (f"Pre-registered confirmatory test at N={top}: exact McNemar "
            f"b={mc['b']}, c={mc['c']}, p={_fmt_p(mc['p_value'])}; paired risk "
            f"difference {st['risk_difference']['diff']:+.2f} "
            f"[{st['risk_difference']['ci'][0]:+.2f}, {st['risk_difference']['ci'][1]:+.2f}].")


_PROSE_PIPELINE = """\
1. **Ingest** — real, pinned public decisions (PEP/RFC/W3C) with machine-readable
   supersession metadata (`Replaces`/`Obsoletes`), reproducible from their pins.
2. **Assemble grounding** — each arm builds the context it will supply (and only
   this step differs between arms).
3. **Answer** — one held-constant answering model behind one held-constant
   scaffold turns (scaffold, grounding, task) into a structured `ProposedChange`.
4. **Score** — deterministic structural scoring: no embeddings, no LLM judge.
5. **Report** — adherence/recall vs corpus size, plus token cost per arm.
"""

_PROSE_METRICS = """\
All scoring is deterministic and structural (ADR-066 — no embeddings, no LLM
judge in scoring):

- **adherence** — did the proposal respect the governing decision (or correctly
  invent none)? The headline.
- **governing-decision recall** — did the arm's grounding actually contain the
  gold governing decision? Explains *why* adherence moves (the Hit@K analog).
- **stale-decision rate** — followed a superseded decision instead of its
  successor.
- **false-permit** — proposed a prohibited action.
- **false-prohibit** — invented a constraint where no decision governs
  (negative-control failure).
- **token cost** — input/output tokens and dollars per answering call; the
  efficiency axis (a strategy that matches adherence for fewer tokens wins).
"""

_PROSE_LIMITS = """\
- **Base-N is an expected tie, not the verdict.** When the corpus is a handful
  of documents, retrieval is trivial and every grounded arm finds the governing
  decision. The thesis is about the *slope* — what happens as the governing
  decision is buried among distractors. Read the curve, not the left edge.
- **The answering model is not seeded.** Opus 4.8 rejects temperature/seed;
  determinism is approximated by a fixed model id + scaffold + structured
  output. Single-cell differences within a point are noise.
- **Scoring is structural.** It checks the shape of the decision (prohibit /
  permit / cite / supersede), not prose quality.
- **If naive RAG does not decay, the report says so.** The head-to-head verdict
  is computed from the numbers, not asserted.
"""


def emit_charts(run: dict, dataset: dict | None, cost_curve: dict | None, out_dir: Path) -> dict:
    """Write the report's SVG charts next to it; return {key: filename}. Each is
    deterministic, dependency-free SVG (scoring.charts)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    charts: dict[str, str] = {}

    # 1. Base-N leaderboard — the decision-quality metrics side by side per arm.
    m = run.get("metrics_by_arm", {})
    if m:
        arms = sorted(m, key=lambda a: m[a]["adherence_rate"], reverse=True)
        svg = grouped_bar_chart(
            "Base-N decision quality by arm",
            arms,
            {
                "adherence": {a: m[a]["adherence_rate"] for a in arms},
                "gov-recall": {a: (m[a].get("governing_recall_rate") or 0) for a in arms},
                "false-permit": {a: m[a]["false_permit_rate"] for a in arms},
            },
            y_label="rate",
        )
        (out_dir / "chart-leaderboard.svg").write_text(svg, encoding="utf-8")
        charts["leaderboard"] = "chart-leaderboard.svg"

    if dataset:
        arms = dataset["arms"]
        # 2. Adherence vs N — the headline.
        svg = line_chart(
            "Decision adherence vs corpus size",
            {a: [(p["N"], p["adherence_rate"]) for p in arms[a]
                 if p.get("adherence_rate") is not None] for a in arms},
            x_label="Corpus size N (log scale)", y_label="adherence rate",
            x_log=True, y_max=1.05,
            bands=_bands(dataset, "adherence_rate"),
        )
        (out_dir / "chart-adherence-vs-n.svg").write_text(svg, encoding="utf-8")
        charts["adherence"] = "chart-adherence-vs-n.svg"

        # 3. Recall vs N — why adherence moves.
        svg = line_chart(
            "Governing-decision recall vs corpus size",
            {a: [(p["N"], p["governing_recall"] or 0) for p in arms[a]] for a in arms},
            x_label="Corpus size N (log scale)", y_label="recall rate",
            x_log=True, y_max=1.05,
            bands=_bands(dataset, "governing_recall"),
        )
        (out_dir / "chart-recall-vs-n.svg").write_text(svg, encoding="utf-8")
        charts["recall"] = "chart-recall-vs-n.svg"

        # 5. rac vs naive_rag head-to-head.
        if "rac" in arms and "naive_rag" in arms:
            svg = line_chart(
                "rac vs naive RAG — adherence vs corpus size",
                {a: [(p["N"], p["adherence_rate"]) for p in arms[a]
                     if p.get("adherence_rate") is not None] for a in ("rac", "naive_rag")},
                x_label="Corpus size N (log scale)", y_label="adherence rate",
                x_log=True, y_max=1.05,
                bands=_bands(dataset, "adherence_rate", arms=("rac", "naive_rag")),
            )
            (out_dir / "chart-rac-vs-rag.svg").write_text(svg, encoding="utf-8")
            charts["head_to_head"] = "chart-rac-vs-rag.svg"

    # 4. Token cost vs N — the efficiency axis (log scale; context_dump blows up).
    if cost_curve:
        svg = line_chart(
            "Token cost vs corpus size (input tokens placed in context)",
            {a: [(n, cost_curve[a][n]) for n in sorted(cost_curve[a])] for a in cost_curve},
            x_label="Corpus size N (log scale)", y_label="mean input tokens (log scale)",
            x_log=True, y_log=True,
        )
        (out_dir / "chart-cost-vs-n.svg").write_text(svg, encoding="utf-8")
        charts["cost"] = "chart-cost-vs-n.svg"

    return charts


def _img(charts: dict, key: str, alt: str) -> list[str]:
    return [f"![{alt}]({charts[key]})", ""] if key in charts else []


def build_report(run: dict, dataset: dict | None, cost_curve: dict | None, charts: dict | None = None,
                 resolution: list[dict] | None = None) -> str:
    charts = charts or {}
    model = run["runs"][0]["answering_model"]["version"] if run["runs"] else "?"
    emb = next((r["embedder"]["name"] for r in run["runs"] if r.get("embedder")), "n/a")
    n_scen = len({r["scenario_id"] for r in run["runs"]})
    cost_md, exact = _cost_table(run)

    parts = [
        "# Decision Grounding Bench",
        "",
        "_Does giving an agent **typed, supersession-aware** grounding make it follow the "
        "right decision better than dumping context or naive RAG — and at what token cost?_",
        "",
        "One held-constant answering model behind one held-constant scaffold. Arms differ "
        "**only** in the grounding they supply. Scoring is deterministic and structural.",
        "",
        f"- **Answering model:** `{model}`  •  **Embedder (RAG/rac retrieval):** `{emb}`",
        f"- **Scenarios:** {n_scen} real, pinned decisions across PEP / RFC / W3C domains",
    ]
    if dataset:
        parts.append(
            f"- **Distractor pool:** {dataset.get('pool_size','?')} real public decisions  •  "
            f"**Corpus sizes (N):** {', '.join(str(n) for n in dataset['ns'])}"
        )
    parts += ["", "---", ""]

    # 1. Headline
    if dataset:
        parts += [
            "## Headline — adherence vs corpus size",
            "",
            *_img(charts, "adherence", "decision adherence vs N"),
            _curve_table(dataset, "adherence_rate", "**Decision adherence**"),
            "",
            *_img(charts, "recall", "governing-decision recall vs N"),
            _curve_table(dataset, "governing_recall", "**Governing-decision recall** (why adherence moves)"),
            "",
        ]

    # 2. Leaderboard
    parts += ["## Leaderboard (base corpus size)", "",
              *_img(charts, "leaderboard", "base-N decision quality by arm"),
              _leaderboard(run), ""]

    # 3. Token cost
    parts += ["## Token cost", "", cost_md, ""]
    if not exact:
        parts.append("_Costs use the deterministic grounding-token estimate; rerun with "
                     "the claude arm to record measured API usage._")
        parts.append("")
    if cost_curve:
        parts += [*_img(charts, "cost", "token cost vs N"), _cost_curve_table(cost_curve, model), ""]

    # 4. rac vs naive_rag
    if dataset:
        parts += ["## rac vs naive RAG (head-to-head)", "",
                  *_img(charts, "head_to_head", "rac vs naive RAG adherence vs N"),
                  _head_to_head(dataset, run), ""]

    # 4a. Per-scenario failure attribution — is one scenario carrying the result?
    if dataset:
        parts += _per_scenario_section(dataset)

    # 4b. Pre-registered paired significance (when the artifacts carry stats).
    parts += _stats_section(run, dataset)

    # 4c. The executable co-primary outcome (when resolution records are given).
    if resolution:
        parts += _resolution_section(resolution)

    # 5-9 prose
    parts += [
        "## Arms", "",
        *[f"- **`{a}`** — {d}" for a, d in _ARM_DESC.items()
          if a in {r["arm"] for r in run["runs"]}],
        "",
        "## Pipeline", "", _PROSE_PIPELINE,
        "## Metrics", "", _PROSE_METRICS,
        "## Dataset", "",
        "Real public engineering decisions with machine-readable supersession metadata, "
        "each pinned to an immutable source and reproducible from its pin. Two decision "
        "types: superseded-decision (a newer decision replaces an older one) and "
        "prohibition (a decision forbids an action). Distractors are real public "
        "decisions drawn from a pinned pool — never synthetic filler.",
        "",
        "## Reproduction", "",
        "```bash",
        "# headline + crossover (needs ANTHROPIC_API_KEY; VOYAGE_API_KEY recommended)",
        "make real-crossover            # synchronous",
        "make real-batch                # same, via Batch API (~50% cost)",
        "# regenerate this report:",
        "python -m scripts.report --run <run.json> --crossover <dataset.json> \\",
        "    --cost-curve --out results/published/decision-grounding-report.md",
        "```",
        "",
        "## Limitations & honesty", "", _PROSE_LIMITS,
    ]
    return "\n".join(parts) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Generate the decision-grounding report.")
    ap.add_argument("--run", required=True, help="compare/batch run JSON")
    ap.add_argument("--crossover", help="crossover dataset JSON")
    ap.add_argument("--cost-curve", action="store_true", help="compute offline token-cost-vs-N")
    ap.add_argument("--pool", help="distractor pool dir (for --cost-curve when the dataset lacks provenance)")
    ap.add_argument("--scenarios", help="scenarios dir (for --cost-curve when the dataset lacks provenance)")
    ap.add_argument("--resolution",
                    help="gitchameleon resolution_records.jsonl — renders the "
                         "decision-conditioned resolution co-primary section")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    run = json.loads(Path(args.run).read_text())
    dataset = json.loads(Path(args.crossover).read_text()) if args.crossover else None
    resolution = None
    if args.resolution:
        resolution = [json.loads(line) for line in
                      Path(args.resolution).read_text().splitlines() if line.strip()]
    curve = None
    if args.cost_curve and dataset:
        curve = _offline_cost_curve(dataset, args.pool, args.scenarios)
        if curve is None:
            print("note: crossover dataset lacks pool/scenario provenance; "
                  "skipping the offline cost curve.", file=sys.stderr)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    charts = emit_charts(run, dataset, curve, out.parent)
    md = build_report(run, dataset, curve, charts, resolution)
    out.write_text(md, encoding="utf-8")
    print(f"wrote {out}  ({len(md):,} bytes)")
    for k, f in charts.items():
        print(f"  chart[{k}] -> {out.parent / f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
