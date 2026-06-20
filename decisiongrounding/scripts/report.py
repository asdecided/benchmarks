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

_ARM_DESC = {
    "context_dump": "pastes the entire corpus into the prompt (the no-retrieval ceiling)",
    "naive_rag": "embeds the corpus and retrieves the top-k chunks (classic RAG)",
    "no_grounding": "supplies nothing — the answering model's parametric memory only (control)",
    "rac": "supplies typed, supersession-aware grounding assembled by the rac CLI",
    "memory_provider": "a pluggable external memory provider (stub)",
}


def _fmt(x, nd=2):
    if x is None:
        return "n/a"
    return f"{x:.{nd}f}"


def _leaderboard(run: dict) -> str:
    m = run["metrics_by_arm"]
    rows = ["| arm | adherence | stale | false-permit | false-prohibit | gov-recall |",
            "|---|--:|--:|--:|--:|--:|"]
    # adherence high to low
    for arm in sorted(m, key=lambda a: m[a]["adherence_rate"], reverse=True):
        d = m[arm]
        rows.append(
            f"| `{arm}` | {_fmt(d['adherence_rate'])} | {_fmt(d['stale_decision_rate'])} | "
            f"{_fmt(d['false_permit_rate'])} | {_fmt(d['false_prohibit_rate'])} | "
            f"{_fmt(d.get('governing_recall_rate'))} |"
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


def _curve_table(dataset: dict, field: str, label: str, nd=2) -> str:
    arms = list(dataset["arms"])
    ns = dataset["ns"]
    head = "| arm | " + " | ".join(f"N={n}" for n in ns) + " |"
    sep = "|---|" + "--:|" * len(ns)
    rows = [f"{label}", "", head, sep]
    for arm in arms:
        pts = {p["N"]: p for p in dataset["arms"][arm]}
        cells = " | ".join(_fmt(pts.get(n, {}).get(field), nd) for n in ns)
        rows.append(f"| `{arm}` | {cells} |")
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
    # auto verdict — strictly from the numbers
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
    return "\n".join(lines)


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
            {a: [(p["N"], p["adherence_rate"]) for p in arms[a]] for a in arms},
            x_label="Corpus size N (log scale)", y_label="adherence rate",
            x_log=True, y_max=1.05,
        )
        (out_dir / "chart-adherence-vs-n.svg").write_text(svg, encoding="utf-8")
        charts["adherence"] = "chart-adherence-vs-n.svg"

        # 3. Recall vs N — why adherence moves.
        svg = line_chart(
            "Governing-decision recall vs corpus size",
            {a: [(p["N"], p["governing_recall"] or 0) for p in arms[a]] for a in arms},
            x_label="Corpus size N (log scale)", y_label="recall rate",
            x_log=True, y_max=1.05,
        )
        (out_dir / "chart-recall-vs-n.svg").write_text(svg, encoding="utf-8")
        charts["recall"] = "chart-recall-vs-n.svg"

        # 5. rac vs naive_rag head-to-head.
        if "rac" in arms and "naive_rag" in arms:
            svg = line_chart(
                "rac vs naive RAG — adherence vs corpus size",
                {a: [(p["N"], p["adherence_rate"]) for p in arms[a]] for a in ("rac", "naive_rag")},
                x_label="Corpus size N (log scale)", y_label="adherence rate",
                x_log=True, y_max=1.05,
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


def build_report(run: dict, dataset: dict | None, cost_curve: dict | None, charts: dict | None = None) -> str:
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
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)

    run = json.loads(Path(args.run).read_text())
    dataset = json.loads(Path(args.crossover).read_text()) if args.crossover else None
    curve = None
    if args.cost_curve and dataset:
        curve = _offline_cost_curve(dataset, args.pool, args.scenarios)
        if curve is None:
            print("note: crossover dataset lacks pool/scenario provenance; "
                  "skipping the offline cost curve.", file=sys.stderr)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    charts = emit_charts(run, dataset, curve, out.parent)
    md = build_report(run, dataset, curve, charts)
    out.write_text(md, encoding="utf-8")
    print(f"wrote {out}  ({len(md):,} bytes)")
    for k, f in charts.items():
        print(f"  chart[{k}] -> {out.parent / f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
