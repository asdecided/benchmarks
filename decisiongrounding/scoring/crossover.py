"""Headline artifact: the adherence-vs-corpus-size crossover curve.

We sweep corpus size N (default {10, 50, 150, 300}) with rising conflict
density and plot per-arm decision-adherence. The corpus is grown with
deterministic, clearly-labelled *filler* artifacts typed as `note` (not
`decision`): they are retrieval distractors, not binding decisions. This models
the mechanism under test — `naive_rag` is typing-blind, so as the corpus grows
its top-k fills with notes and the binding decision falls out; `context_dump`
supplies everything and the decision-reading agent ignores non-decisions, so it
holds. (A typed `rac` arm, once built, should hold for the same reason.)

The full N=300 corpus is illustrative synthetic padding, not a real corpus.
Real curves require real/public-derived corpora — see CONTRIBUTING.md.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path
from typing import Callable

from providers import build_provider, make_answering_model
from providers.base import CorpusArtifact
from scenarios.loader import Scenario
from scoring.scorer import score

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {"the", "a", "an", "to", "of", "and", "or", "for", "in", "on", "with", "is", "are"}
DEFAULT_NS = (10, 50, 150, 300)
DISCRIMINATING = {"superseded_decision", "prohibition_at_point_of_action", "conflicting_scoped"}


def _domain_tokens(scenario: Scenario) -> list[str]:
    text = f"{scenario.task.prompt} {scenario.task.proposed_action}".lower()
    toks = [t for t in _TOKEN.findall(text) if t not in _STOP and len(t) > 2]
    return sorted(set(toks))


def make_filler_notes(
    count: int, scenario: Scenario, seed: int, density: float
) -> list[CorpusArtifact]:
    """Deterministic distractor `note` artifacts (never typed as decisions).

    `density` (0..1) rises with N. A `density` fraction of the notes are *strong
    distractors* that closely echo the task — exactly the chatter a typing-blind
    retriever cannot distinguish from a binding decision; the rest are weak,
    low-similarity notes. As N (and density) grow, strong distractors crowd
    `naive_rag`'s fixed top-k and the binding decision falls out. The
    decision-reading agent ignores all notes, so `context_dump` is unaffected —
    the divergence is entirely a retrieval/typing effect.
    """
    pool = _domain_tokens(scenario)
    rng = random.Random(f"{seed}:{scenario.scenario_id}:{count}")
    action = scenario.task.proposed_action
    n_strong = int(round(count * density))
    notes: list[CorpusArtifact] = []
    for i in range(count):
        if i < n_strong:
            body = (
                f"# Note {i:04d}\n\nSlack thread: someone mentioned wanting to "
                f"{action}. Informal chatter — this is not a decision and binds "
                f"nothing.\n"
            )
        else:
            k = min(len(pool), rng.randint(1, max(1, len(pool) // 3))) if pool else 0
            sample = rng.sample(pool, k) if pool else []
            body = (
                f"# Note {i:04d}\n\nMiscellaneous notes on {' '.join(sample)}. "
                f"Not a decision.\n"
            )
        notes.append(
            CorpusArtifact(
                id=f"NOTE-{i:04d}",
                type="note",
                path="(synthetic-filler)",
                text=body,
                filler=True,
            )
        )
    return notes


def make_real_distractors(
    pool: list[CorpusArtifact], count: int, scenario: Scenario, seed: int
) -> list[CorpusArtifact]:
    """Deterministically draw `count` REAL public-decision distractors from the
    pool — the honest replacement for synthetic `note` padding.

    These are genuine PEP `decision` artifacts, so they are far harder retrieval
    distractors than chatter: a typing-blind retriever cannot dismiss them as
    non-decisions, and they compete with the binding decision on real topical
    similarity. The scenario's own corpus ids (the binding decision and the one
    it supersedes) are excluded so a distractor never collides with the signal.
    Selection is a seeded shuffle keyed by (seed, scenario, count), so the pool
    membership at each N is fixed and reproducible.
    """
    own = {a.id for a in scenario.corpus}
    candidates = [a for a in pool if a.id not in own]
    rng = random.Random(f"{seed}:{scenario.scenario_id}:real:{count}")
    rng.shuffle(candidates)
    return candidates[: max(0, count)]


def _run_arm_on_corpus(arm_name: str, corpus, scenario, answering_model, embedder_spec: str):
    provider = build_provider(arm_name, answering_model, embedder_spec)
    provider.prepare(list(corpus))
    pc = provider.respond(scenario.task)
    gov = scenario.gold_label.governing_decision
    retrieved = None if gov is None else (gov in provider.grounding.artifacts_supplied)
    # Token cost of what this arm placed in context — the deterministic estimate
    # always, plus the real API usage when the answering model reports it.
    token_estimate = provider.grounding.token_estimate
    usage = getattr(answering_model, "last_usage", None)
    return score(scenario, pc), retrieved, token_estimate, usage


def build_dataset(
    scenarios: list[Scenario],
    arms: tuple[str, ...] = ("context_dump", "naive_rag"),
    ns: tuple[int, ...] = DEFAULT_NS,
    seed: int = 0,
    answering_model_name: str = "offline-stub",
    embedder_spec: str = "local-hash",
    pool: list[CorpusArtifact] | None = None,
    pool_dir: str | None = None,
    scenarios_dir: str | None = None,
    progress: "Callable[[dict], None] | None" = None,
) -> dict:
    """Compute per-arm adherence at each N, averaged over discriminating scenarios.

    Defaults keep the offline spine (scripted model + local-hash embedder). Pass
    `answering_model_name="claude"` and an `embedder_spec` like
    `voyage:voyage-4-large` to produce a real-model crossover.

    Distractors: by default each N is padded with synthetic `note` filler
    (illustrative). Pass a real PEP `pool` (see `scenarios.loader.load_pool`) to
    scale N with REAL public-decision distractors — the honest curve. The pool
    must be large enough for the biggest N; otherwise the available real
    distractors cap the corpus and that N's real size is recorded as achieved.

    `progress`: optional callback invoked once per completed cell with a record
    {record, idx, total, N, arm, scenario_id, adherent, stale_decision_followed,
    governing_decision_retrieved, token_estimate, usage, error}. The runner uses
    it to stream a durable `.partial.jsonl` and a live progress line, so a long
    real sweep is observable and never lost mid-run.
    """
    use_real = pool is not None
    if use_real:
        max_real = len(pool) + max(len(s.corpus) for s in scenarios) if pool else 0
        if max(ns) > max_real:
            raise ValueError(
                f"real pool too small for N={max(ns)}: pool has {len(pool)} "
                f"distractors. Build a wider pool (python -m ingest.peps pool "
                f"build --range 1-700) or lower --ns."
            )
    discriminating = [s for s in scenarios if s.scenario_type in DISCRIMINATING]
    # One answering model instance reused across the sweep (lazy client for real).
    answering_model = make_answering_model(answering_model_name, seed)
    points: dict[str, list[dict]] = {arm: [] for arm in arms}
    # per_scenario[arm][scenario_id] -> [{N, adherent, stale}]
    per_scenario: dict[str, dict[str, list[dict]]] = {
        arm: {s.scenario_id: [] for s in discriminating} for arm in arms
    }
    errors: list[dict] = []
    n_max = max(ns)
    total_cells = len(ns) * len(arms) * len(discriminating)
    idx = 0
    for n in ns:
        density = (n - min(ns)) / (n_max - min(ns)) if n_max != min(ns) else 0.0
        for arm in arms:
            adhered = 0
            retrieved_flags: list = []
            token_estimates: list[int] = []
            usages: list[dict] = []
            for sc in discriminating:
                idx += 1
                pad = max(0, n - len(sc.corpus))
                if use_real:
                    distractors = make_real_distractors(pool, pad, sc, seed)
                else:
                    distractors = make_filler_notes(pad, sc, seed, density)
                corpus = list(sc.corpus) + distractors
                cell_error = None
                try:
                    sc_score, gov_retrieved, tok_est, usage = _run_arm_on_corpus(
                        arm, corpus, sc, answering_model, embedder_spec
                    )
                    adherent = sc_score.adherent
                    stale = sc_score.stale_decision_followed
                except Exception as exc:  # noqa: BLE001 - one cell must not lose the curve
                    cell_error = repr(exc)
                    errors.append(
                        {"arm": arm, "scenario_id": sc.scenario_id, "N": n, "error": cell_error}
                    )
                    adherent = False
                    stale = False
                    gov_retrieved = None
                    tok_est = 0
                    usage = None
                adhered += 1 if adherent else 0
                retrieved_flags.append(gov_retrieved)
                token_estimates.append(tok_est)
                if usage:
                    usages.append(usage)
                per_scenario[arm][sc.scenario_id].append(
                    {
                        "N": n,
                        "adherent": adherent,
                        "stale_decision_followed": stale,
                        "governing_decision_retrieved": gov_retrieved,
                    }
                )
                if progress is not None:
                    progress(
                        {
                            "record": "cell",
                            "idx": idx,
                            "total": total_cells,
                            "N": n,
                            "arm": arm,
                            "scenario_id": sc.scenario_id,
                            "adherent": adherent,
                            "stale_decision_followed": stale,
                            "governing_decision_retrieved": gov_retrieved,
                            "token_estimate": tok_est,
                            "usage": usage,
                            "error": cell_error,
                        }
                    )
            rate = adhered / len(discriminating) if discriminating else 0.0
            governed = [f for f in retrieved_flags if f is not None]
            recall = (sum(1 for f in governed if f) / len(governed)) if governed else None
            # Mean grounding tokens this arm placed in context at this N — the
            # deterministic estimate, plus real API usage means when available.
            tok_mean = sum(token_estimates) / len(token_estimates) if token_estimates else 0
            point = {
                "N": n,
                "adherence_rate": rate,
                "governing_recall": recall,
                "token_estimate_mean": tok_mean,
            }
            if usages:
                point["input_tokens_mean"] = sum(u["input_tokens"] for u in usages) / len(usages)
                point["output_tokens_mean"] = sum(u["output_tokens"] for u in usages) / len(usages)
            points[arm].append(point)
    return {
        "metric": "decision_adherence_rate",
        "scenarios_included": [s.scenario_id for s in discriminating],
        "distractors": "real-decision-pool" if use_real else "synthetic-note-filler",
        "pool_size": len(pool) if use_real else 0,
        "note": (
            "Distractors are REAL public decision artifacts (PEP/RFC) drawn from "
            "the pinned pool — a real adherence-vs-N curve."
            if use_real
            else "Filler is synthetic untyped `note` padding. Illustrative, not a real corpus."
        ),
        "seed": seed,
        "ns": list(ns),
        "answering_model": answering_model.version,
        "embedder": embedder_spec,
        # Provenance so the cost-vs-N curve can be recomputed offline (no spend).
        "pool_dir": pool_dir,
        "scenarios_dir": scenarios_dir,
        "arms": {arm: points[arm] for arm in arms},
        "per_scenario": per_scenario,
        "errors": errors,
    }


def render_chart(dataset: dict, out_path: str | Path) -> Path:
    """Render ONE crossover chart. matplotlib if present, else pure-Python SVG."""
    out_path = Path(out_path)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 4.5))
        for arm, pts in dataset["arms"].items():
            ax.plot([p["N"] for p in pts], [p["adherence_rate"] for p in pts], marker="o", label=arm)
        ax.set_xscale("log")
        ax.set_xlabel("Corpus size N (log scale)")
        ax.set_ylabel("Decision-adherence rate")
        ax.set_ylim(-0.05, 1.05)
        ax.set_title("Decision adherence vs corpus size (illustrative scaffold)")
        ax.legend()
        ax.grid(True, alpha=0.3)
        png = out_path.with_suffix(".png")
        fig.tight_layout()
        fig.savefig(png, dpi=120)
        plt.close(fig)
        return png
    except Exception:
        svg = out_path.with_suffix(".svg")
        svg.write_text(_render_svg(dataset), encoding="utf-8")
        return svg


def _render_svg(dataset: dict) -> str:
    import math

    W, H, pad = 720, 460, 60
    ns = dataset["ns"]
    xs = [math.log10(n) for n in ns]
    xmin, xmax = min(xs), max(xs)

    def px(x):
        return pad + (x - xmin) / (xmax - xmin or 1) * (W - 2 * pad)

    def py(y):
        return H - pad - y * (H - 2 * pad)

    colors = {"context_dump": "#1f77b4", "naive_rag": "#d62728", "rac": "#2ca02c"}
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" font-family="sans-serif">',
        f'<rect width="{W}" height="{H}" fill="white"/>',
        f'<text x="{W/2}" y="28" text-anchor="middle" font-size="16">Decision adherence vs corpus size (illustrative scaffold)</text>',
        f'<line x1="{pad}" y1="{py(0)}" x2="{W-pad}" y2="{py(0)}" stroke="#333"/>',
        f'<line x1="{pad}" y1="{py(0)}" x2="{pad}" y2="{py(1)}" stroke="#333"/>',
        f'<text x="{pad-8}" y="{py(1)}" text-anchor="end" font-size="11">1.0</text>',
        f'<text x="{pad-8}" y="{py(0)}" text-anchor="end" font-size="11">0.0</text>',
        f'<text x="{W/2}" y="{H-15}" text-anchor="middle" font-size="12">Corpus size N (log scale)</text>',
    ]
    for n, x in zip(ns, xs):
        parts.append(f'<text x="{px(x)}" y="{py(0)+18}" text-anchor="middle" font-size="11">{n}</text>')
    legend_y = 44
    for arm, pts in dataset["arms"].items():
        color = colors.get(arm, "#555")
        poly = " ".join(f"{px(math.log10(p['N']))},{py(p['adherence_rate'])}" for p in pts)
        parts.append(f'<polyline points="{poly}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for p in pts:
            parts.append(f'<circle cx="{px(math.log10(p["N"]))}" cy="{py(p["adherence_rate"])}" r="3.5" fill="{color}"/>')
        parts.append(f'<text x="{W-pad-120}" y="{legend_y}" font-size="12" fill="{color}">{arm}</text>')
        legend_y += 16
    parts.append("</svg>")
    return "\n".join(parts)


def emit(dataset: dict, out_dir: str | Path) -> tuple[Path, Path]:
    """Write the dataset JSON and the chart; return both paths."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data_path = out_dir / "crossover_dataset.json"
    data_path.write_text(json.dumps(dataset, indent=2), encoding="utf-8")
    chart_path = render_chart(dataset, out_dir / "crossover")
    return data_path, chart_path
