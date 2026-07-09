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
import time
from pathlib import Path
from typing import Callable

from providers import build_provider, make_answering_model
from providers.answering import usage_dict
from providers.base import SCAFFOLD, ContextWindowExceededError, CorpusArtifact, check_context_window
from scenarios.loader import Scenario
from scoring.metrics import summarize
from scoring.scorer import score
from scoring.stats import stats_by_n
from util.io import atomic_write_text

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


def _corpus_for(n, sc, ns, seed, pool, use_real):
    """The corpus for one sweep cell: the scenario's own artifacts plus padding to
    size N — real public-decision distractors, or synthetic note filler."""
    pad = max(0, n - len(sc.corpus))
    if use_real:
        distractors = make_real_distractors(pool, pad, sc, seed)
    else:
        n_max, n_min = max(ns), min(ns)
        density = (n - n_min) / (n_max - n_min) if n_max != n_min else 0.0
        distractors = make_filler_notes(pad, sc, seed, density)
    return list(sc.corpus) + distractors


def _point(n, adhered, total, retrieved_flags, token_estimates, usages, cwe_count=0):
    """One (arm, N) curve point — shared by the sync and batched builders so the
    two produce byte-identical shapes.

    `cwe_count`: of `total` cells, how many hit the answering model's context
    window (see `ContextWindowExceededError`) and so were never answered.
    Those cells are excluded from BOTH the numerator and denominator of
    `adherence_rate` — folding them in as "non-adherent" would misreport a
    structural ceiling (the arm literally cannot fit at this N) as the arm
    answering and getting it wrong, corrupting exactly the comparison this
    curve exists to make. When every cell at this N hit the ceiling,
    `adherence_rate` is None (no rate to report) rather than a misleading 0.0.
    """
    attempted = total - cwe_count
    rate = (adhered / attempted) if attempted else None
    governed = [f for f in retrieved_flags if f is not None]
    recall = (sum(1 for f in governed if f) / len(governed)) if governed else None
    tok_mean = sum(token_estimates) / len(token_estimates) if token_estimates else 0
    point = {
        "N": n, "adherence_rate": rate, "governing_recall": recall,
        "token_estimate_mean": tok_mean,
        # Always present (0 when nothing hit the ceiling), not conditional —
        # so multi-seed aggregation (_AGG_FIELDS) sees a real 0 for a seed
        # with no context-window-exceeded cells, rather than silently
        # skipping that seed as if it had no opinion (see _columns_from_datasets).
        "context_window_exceeded_count": cwe_count,
        "context_window_exceeded_rate": (cwe_count / total) if total else 0.0,
    }
    if usages:
        point["input_tokens_mean"] = sum(u["input_tokens"] for u in usages) / len(usages)
        point["output_tokens_mean"] = sum(u["output_tokens"] for u in usages) / len(usages)
    return point


def _envelope(discriminating, use_real, pool, seed, ns, model_version, embedder_spec,
              pool_dir, scenarios_dir, arms, points, per_scenario, errors, cells):
    """The dataset dict both builders return."""
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
        "answering_model": model_version,
        "embedder": embedder_spec,
        # Provenance so the cost-vs-N curve can be recomputed offline (no spend).
        "pool_dir": pool_dir,
        "scenarios_dir": scenarios_dir,
        "arms": {arm: points[arm] for arm in arms},
        "per_scenario": per_scenario,
        "errors": errors,
        # Raw per-cell booleans — the statistical record the pre-registered
        # paired analysis (spec/analysis-plan-amendment-1.md) runs on. The
        # aggregated fractions above are for display; these are for inference.
        "cells": cells,
        "stats": stats_by_n(cells) if cells else None,
    }


def _check_pool(pool, ns, scenarios, use_real):
    if use_real and max(ns) > (len(pool) + max(len(s.corpus) for s in scenarios) if pool else 0):
        raise ValueError(
            f"real pool too small for N={max(ns)}: pool has {len(pool)} "
            f"distractors. Build a wider pool (python -m ingest.peps pool "
            f"build --range 1-700) or lower --ns."
        )


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
    resume: "dict[tuple[int, int, str, str], dict] | None" = None,
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

    `resume`: optional cache of already-completed cells from a previous
    (crashed) run's `.partial.jsonl`, keyed by (seed, N, arm, scenario_id) —
    see `runner.cli._load_resume_cells`. A cached cell is replayed instead of
    re-run: successful cells and context-window-exceeded cells (a
    deterministic structural property of the corpus/arm — re-running only
    re-burns work to reach the same preflight failure) are injected verbatim;
    cells that failed with any other error are re-run live, since recovering
    transient failures is the point of resuming. Replayed cells still fire
    `progress` (tagged `"cached": true`) so the new sidecar is self-contained
    and a second crash resumes from the newest sidecar alone.
    """
    use_real = pool is not None
    _check_pool(pool, ns, scenarios, use_real)
    discriminating = [s for s in scenarios if s.scenario_type in DISCRIMINATING]
    # One answering model instance reused across the sweep (lazy client for real).
    answering_model = make_answering_model(answering_model_name, seed)
    points: dict[str, list[dict]] = {arm: [] for arm in arms}
    per_scenario: dict[str, dict[str, list[dict]]] = {
        arm: {s.scenario_id: [] for s in discriminating} for arm in arms
    }
    errors: list[dict] = []
    cell_records: list[dict] = []
    total_cells = len(ns) * len(arms) * len(discriminating)
    idx = 0
    for n in ns:
        for arm in arms:
            adhered = 0
            cwe_count = 0
            retrieved_flags: list = []
            token_estimates: list[int] = []
            usages: list[dict] = []
            for sc in discriminating:
                idx += 1
                cell_error = None
                cell_kind = None
                hit = resume.get((seed, n, arm, sc.scenario_id)) if resume else None
                # Replay only completed cells: successes and context-window
                # hits (deterministic — re-running reaches the same preflight
                # failure). A cell that died with any other error is re-run.
                cached = hit is not None and (
                    hit.get("error") is None
                    or hit.get("kind") == "context_window_exceeded"
                )
                if cached:
                    adherent = hit["adherent"]
                    stale = hit["stale_decision_followed"]
                    gov_retrieved = hit["governing_decision_retrieved"]
                    tok_est = hit["token_estimate"]
                    usage = hit.get("usage")
                    cell_error = hit.get("error")
                    cell_kind = hit.get("kind")
                    if cell_kind == "context_window_exceeded":
                        cwe_count += 1
                        errors.append({
                            "arm": arm, "scenario_id": sc.scenario_id, "N": n,
                            "error": cell_error, "kind": cell_kind,
                        })
                else:
                    corpus = _corpus_for(n, sc, ns, seed, pool, use_real)
                    try:
                        sc_score, gov_retrieved, tok_est, usage = _run_arm_on_corpus(
                            arm, corpus, sc, answering_model, embedder_spec
                        )
                        adherent = sc_score.adherent
                        stale = sc_score.stale_decision_followed
                    except ContextWindowExceededError as exc:
                        cell_error = repr(exc)
                        cell_kind = "context_window_exceeded"
                        cwe_count += 1
                        errors.append({
                            "arm": arm, "scenario_id": sc.scenario_id, "N": n,
                            "error": cell_error, "kind": cell_kind,
                        })
                        adherent = stale = False
                        gov_retrieved = None
                        tok_est = exc.token_estimate
                        usage = None
                    except Exception as exc:  # noqa: BLE001 - one cell must not lose the curve
                        cell_error = repr(exc)
                        errors.append(
                            {"arm": arm, "scenario_id": sc.scenario_id, "N": n,
                             "error": cell_error}
                        )
                        adherent = stale = False
                        gov_retrieved = None
                        tok_est = 0
                        usage = None
                if cell_kind != "context_window_exceeded":
                    adhered += 1 if adherent else 0
                retrieved_flags.append(gov_retrieved)
                token_estimates.append(tok_est)
                if usage:
                    usages.append(usage)
                per_scenario[arm][sc.scenario_id].append(
                    {"N": n, "adherent": adherent, "stale_decision_followed": stale,
                     "governing_decision_retrieved": gov_retrieved}
                )
                # A context-window-exceeded cell was never answered — it has no
                # real adherent value (forced False above only for the summary
                # counters), so it is excluded from the paired-statistics record
                # entirely rather than biasing a McNemar/effect-size comparison
                # with a fabricated non-adherent outcome (mirrors `adhered`'s own
                # exclusion just above, and `_point`'s adherence_rate handling).
                if cell_kind != "context_window_exceeded":
                    cell_records.append({"seed": seed, "N": n, "arm": arm,
                                         "scenario_id": sc.scenario_id, "adherent": adherent})
                if progress is not None:
                    rec = {"record": "cell", "idx": idx, "total": total_cells, "N": n,
                           "arm": arm, "scenario_id": sc.scenario_id, "adherent": adherent,
                           "stale_decision_followed": stale,
                           "governing_decision_retrieved": gov_retrieved,
                           "token_estimate": tok_est, "usage": usage, "error": cell_error,
                           "kind": cell_kind}
                    if cached:
                        rec["cached"] = True
                    progress(rec)
            points[arm].append(_point(n, adhered, len(discriminating), retrieved_flags,
                                      token_estimates, usages, cwe_count=cwe_count))
    return _envelope(discriminating, use_real, pool, seed, ns, answering_model.version,
                     embedder_spec, pool_dir, scenarios_dir, arms, points, per_scenario, errors,
                     cell_records)


def build_dataset_batched(
    scenarios: list[Scenario],
    arms: tuple[str, ...],
    ns: tuple[int, ...] = DEFAULT_NS,
    seed: int = 0,
    embedder_spec: str = "local-hash",
    pool: list[CorpusArtifact] | None = None,
    pool_dir: str | None = None,
    scenarios_dir: str | None = None,
    poll: int = 20,
    progress: "Callable[[dict], None] | None" = None,
) -> dict:
    """Same adherence-vs-N curve as build_dataset, but the held-constant answering
    calls go through the Message Batches API (≈50% of standard price, and it runs
    server-side so it survives a client restart). Grounding assembly (rac CLI /
    embeddings) still happens locally up front; only the answering is batched.

    Pinned to the claude model — the offline stub has nothing to batch.
    """
    use_real = pool is not None
    _check_pool(pool, ns, scenarios, use_real)
    discriminating = [s for s in scenarios if s.scenario_type in DISCRIMINATING]
    model = make_answering_model("claude", seed)

    # Pass A (local, no API): assemble every cell's grounding + request, in sweep
    # order. A cell whose grounding assembly fails is recorded and not submitted.
    cells: list[dict] = []
    for n in ns:
        for arm in arms:
            for sc in discriminating:
                cell = {"cid": f"c{len(cells)}", "n": n, "arm": arm, "sc": sc,
                        "tok": 0, "gov": None, "req": None, "error": None, "kind": None}
                try:
                    provider = build_provider(arm, model, embedder_spec)
                    provider.prepare(_corpus_for(n, sc, ns, seed, pool, use_real))
                    grounding = provider.assemble(sc.task)
                    # Same symmetric preflight as the synchronous path
                    # (Provider.respond) — batching bypasses respond(), so it is
                    # checked here instead, before the cell is ever submitted.
                    check_context_window(grounding, sc.task, model)
                    gov = sc.gold_label.governing_decision
                    cell["gov"] = None if gov is None else (gov in grounding.artifacts_supplied)
                    cell["tok"] = grounding.token_estimate
                    cell["req"] = model.build_request(SCAFFOLD, grounding, sc.task)
                except ContextWindowExceededError as exc:
                    cell["error"] = repr(exc)
                    cell["kind"] = "context_window_exceeded"
                    cell["tok"] = exc.token_estimate
                except Exception as exc:  # noqa: BLE001 - one cell must not lose the run
                    cell["error"] = repr(exc)
                cells.append(cell)

    # Submit one batch for the cells that assembled; poll until it ends.
    client = model._ensure_client()
    requests = [{"custom_id": c["cid"], "params": c["req"]} for c in cells if c["req"] is not None]
    answers: dict[str, tuple] = {}  # cid -> (ProposedChange|None, usage|None, error|None)
    if requests:
        batch = client.messages.batches.create(requests=requests)
        while client.messages.batches.retrieve(batch.id).processing_status != "ended":
            time.sleep(max(5, poll))
        for r in client.messages.batches.results(batch.id):
            if r.result.type != "succeeded":
                answers[r.custom_id] = (None, None, f"batch result: {r.result.type}")
                continue
            try:
                pc = model.parse_message(r.result.message)
                answers[r.custom_id] = (pc, usage_dict(getattr(r.result.message, "usage", None)), None)
            except Exception as exc:  # noqa: BLE001
                answers[r.custom_id] = (None, None, repr(exc))

    # Aggregate in the same sweep order, scoring each cell from its batch answer.
    points: dict[str, list[dict]] = {arm: [] for arm in arms}
    per_scenario: dict[str, dict[str, list[dict]]] = {
        arm: {s.scenario_id: [] for s in discriminating} for arm in arms
    }
    errors: list[dict] = []
    cell_records: list[dict] = []
    total_cells = len(cells)
    it = iter(cells)
    idx = 0
    for n in ns:
        for arm in arms:
            adhered = 0
            cwe_count = 0
            retrieved_flags: list = []
            token_estimates: list[int] = []
            usages: list[dict] = []
            for sc in discriminating:
                cell = next(it)
                idx += 1
                is_cwe = cell.get("kind") == "context_window_exceeded"
                pc, usage, err = answers.get(cell["cid"], (None, None, cell["error"]))
                cell_error = err or cell["error"]
                if is_cwe:
                    cwe_count += 1
                    errors.append({"arm": arm, "scenario_id": sc.scenario_id, "N": n,
                                   "error": cell_error, "kind": "context_window_exceeded"})
                    adherent = stale = False
                    gov_retrieved = None
                    tok_est = cell["tok"]
                    usage = None
                elif pc is None:
                    errors.append({"arm": arm, "scenario_id": sc.scenario_id, "N": n,
                                   "error": cell_error or "no batch result"})
                    adherent = stale = False
                    gov_retrieved = None
                    tok_est = 0
                    usage = None
                else:
                    sc_score = score(sc, pc)
                    adherent = sc_score.adherent
                    stale = sc_score.stale_decision_followed
                    gov_retrieved = cell["gov"]
                    tok_est = cell["tok"]
                if not is_cwe:
                    adhered += 1 if adherent else 0
                retrieved_flags.append(gov_retrieved)
                token_estimates.append(tok_est)
                if usage:
                    usages.append(usage)
                per_scenario[arm][sc.scenario_id].append(
                    {"N": n, "adherent": adherent, "stale_decision_followed": stale,
                     "governing_decision_retrieved": gov_retrieved}
                )
                # Same exclusion as build_dataset: a cell that never got
                # answered is not a paired-statistics observation.
                if not is_cwe:
                    cell_records.append({"seed": seed, "N": n, "arm": arm,
                                         "scenario_id": sc.scenario_id, "adherent": adherent})
                if progress is not None:
                    progress({"record": "cell", "idx": idx, "total": total_cells, "N": n,
                              "arm": arm, "scenario_id": sc.scenario_id, "adherent": adherent,
                              "stale_decision_followed": stale,
                              "governing_decision_retrieved": gov_retrieved,
                              "token_estimate": tok_est, "usage": usage, "error": cell_error,
                              "kind": cell.get("kind")})
            points[arm].append(_point(n, adhered, len(discriminating), retrieved_flags,
                                      token_estimates, usages, cwe_count=cwe_count))
    return _envelope(discriminating, use_real, pool, seed, ns, model.version,
                     embedder_spec, pool_dir, scenarios_dir, arms, points, per_scenario, errors,
                     cell_records)


# --- multi-seed aggregation -------------------------------------------------
# Fields aggregated across seeds. The plain key stays the MEAN (back-compat);
# `<field>_ci` / `_std` / `_values` are added alongside.
_AGG_FIELDS = ("adherence_rate", "governing_recall", "token_estimate_mean",
               "input_tokens_mean", "context_window_exceeded_count",
               "context_window_exceeded_rate")


def _seed_points(ds: dict, arm: str) -> dict:
    return {p["N"]: p for p in ds["arms"].get(arm, [])}


def _tag_seed(cb, seed):
    """Wrap a progress callback so each cell record carries its seed."""
    if cb is None:
        return None

    def wrapped(rec):
        rec = dict(rec)
        rec["seed"] = seed
        cb(rec)

    return wrapped


def build_dataset_multiseed(
    scenarios: list[Scenario],
    arms: tuple[str, ...],
    ns: tuple[int, ...] = DEFAULT_NS,
    seeds: "tuple[int, ...] | list[int]" = (0,),
    *,
    answering_model_name: str = "offline-stub",
    embedder_spec: str = "local-hash",
    pool: list[CorpusArtifact] | None = None,
    pool_dir: str | None = None,
    scenarios_dir: str | None = None,
    batched: bool = False,
    poll: int = 20,
    pair: tuple[str, str] = ("rac", "naive_rag"),
    progress: "Callable[[dict], None] | None" = None,
    resume: "dict[tuple[int, int, str, str], dict] | None" = None,
) -> dict:
    """Run the crossover over several seeds and aggregate per (arm, N) into
    mean +/- a t-based 95% CI. The plain fields stay the mean (backward
    compatible); `<field>_ci` / `_std` / `_values`, `n_seeds`, `seeds`, and a
    paired `pair[0]`-vs-`pair[1]` adherence difference (`paired`) are added.

    Calls the single-seed builders per seed, so batched + multiseed compose.
    Offline runs (deterministic stub + embedder) show little spread; the
    aggregation is exercised regardless.
    """
    uniq = list(dict.fromkeys(int(s) for s in seeds)) or [0]
    per_seed = run_seeds(
        scenarios, arms, ns, uniq,
        answering_model_name=answering_model_name, embedder_spec=embedder_spec,
        pool=pool, pool_dir=pool_dir, scenarios_dir=scenarios_dir,
        batched=batched, poll=poll, progress=progress, resume=resume)
    return _aggregate_seeds(per_seed, list(arms), list(ns), pair)


def run_seeds(
    scenarios, arms, ns, seeds, *,
    answering_model_name: str = "offline-stub", embedder_spec: str = "local-hash",
    pool=None, pool_dir=None, scenarios_dir=None,
    batched: bool = False, poll: int = 20, progress=None, resume=None,
) -> list[tuple[int, dict]]:
    """Build one single-seed crossover dataset per seed (seed-tagged progress).
    The per-seed datasets feed `_aggregate_seeds` / `merge_seed_datasets`."""
    out: list[tuple[int, dict]] = []
    for s in seeds:
        if batched:
            ds = build_dataset_batched(
                scenarios, arms=arms, ns=ns, seed=s, embedder_spec=embedder_spec,
                pool=pool, pool_dir=pool_dir, scenarios_dir=scenarios_dir,
                poll=poll, progress=_tag_seed(progress, s))
        else:
            ds = build_dataset(
                scenarios, arms=arms, ns=ns, seed=s,
                answering_model_name=answering_model_name, embedder_spec=embedder_spec,
                pool=pool, pool_dir=pool_dir, scenarios_dir=scenarios_dir,
                progress=_tag_seed(progress, s), resume=resume)
        out.append((int(s), ds))
    return out


def _columns_from_datasets(per_seed, arms, ns) -> dict:
    """cols[arm][N][field] = [per-seed values] (None dropped — governing_recall
    when nothing is governed, or adherence_rate when every cell at this
    (arm, N) hit the context window in that seed — see `_point`)."""
    cols = {arm: {n: {} for n in ns} for arm in arms}
    for arm in arms:
        for _, ds in per_seed:
            by_n = _seed_points(ds, arm)
            for n in ns:
                p = by_n.get(n, {})
                for field in _AGG_FIELDS:
                    if field not in p:
                        continue
                    v = p[field]
                    if v is None:
                        continue
                    cols[arm][n].setdefault(field, []).append(v)
    return cols


def _aggregate_arm_points(arms, ns, cols, n_seeds) -> dict:
    points = {}
    for arm in arms:
        pts = []
        for n in ns:
            point = {"N": n, "n_seeds": n_seeds}
            for field in _AGG_FIELDS:
                vals = cols[arm][n].get(field)
                if not vals:
                    # No seed produced a value at all (nothing governed here for
                    # governing_recall; every seed hit the context window for
                    # adherence_rate) — an explicit None, not a missing key or a
                    # misleading 0.0.
                    if field in ("governing_recall", "adherence_rate"):
                        point[field] = None
                    continue
                s = summarize(vals)
                point[field] = s["mean"]
                point[f"{field}_std"] = s["std"]
                point[f"{field}_ci"] = s["ci"]
                point[f"{field}_values"] = s["values"]
            pts.append(point)
        points[arm] = pts
    return points


def _paired(per_seed, ns, pair) -> dict | None:
    """Per-N paired adherence difference pair[0]-pair[1], differenced within each
    seed (common random numbers), with its own CI."""
    a, b = pair
    if not per_seed or not all(a in ds["arms"] and b in ds["arms"] for _, ds in per_seed):
        return None
    out = []
    for n in ns:
        diffs = []
        for _, ds in per_seed:
            pa, pb = _seed_points(ds, a).get(n), _seed_points(ds, b).get(n)
            if pa and pb and pa.get("adherence_rate") is not None and pb.get("adherence_rate") is not None:
                diffs.append(pa["adherence_rate"] - pb["adherence_rate"])
        if diffs:
            s = summarize(diffs)
            out.append({"N": n, "diff_mean": s["mean"], "diff_ci": s["ci"],
                        "diff_std": s["std"], "n": s["n"], "values": s["values"]})
    return {f"{a}_vs_{b}": out} if out else None


def _agg_per_scenario(per_seed, arms) -> dict:
    """Per (arm, scenario, N): adherent/stale fraction across seeds (used by the
    `demo` printout)."""
    out = {}
    for arm in arms:
        out[arm] = {}
        for sid in per_seed[0][1]["per_scenario"].get(arm, {}):
            by_n = {}
            for _, ds in per_seed:
                for rec in ds["per_scenario"][arm][sid]:
                    by_n.setdefault(rec["N"], []).append(rec)
            recs = []
            for n in sorted(by_n):
                g = by_n[n]
                adh = sum(1 for r in g if r["adherent"]) / len(g)
                stale = sum(1 for r in g if r["stale_decision_followed"]) / len(g)
                govs = [r["governing_decision_retrieved"] for r in g
                        if r["governing_decision_retrieved"] is not None]
                gov = (sum(1 for x in govs if x) / len(govs)) if govs else None
                recs.append({"N": n, "adherent": adh, "stale_decision_followed": stale,
                             "governing_decision_retrieved": gov, "n_seeds": len(g)})
            out[arm][sid] = recs
    return out


def _aggregate_seeds(per_seed, arms, ns, pair) -> dict:
    base = dict(per_seed[0][1])
    cols = _columns_from_datasets(per_seed, arms, ns)
    base["arms"] = _aggregate_arm_points(arms, ns, cols, len(per_seed))
    base["per_scenario"] = _agg_per_scenario(per_seed, arms)
    base["errors"] = [e for _, ds in per_seed for e in ds["errors"]]
    base["seeds"] = [s for s, _ in per_seed]
    base["n_seeds"] = len(per_seed)
    base["seed"] = per_seed[0][0]
    # Concatenate the seed-tagged per-cell booleans; the paired unit for the
    # cross-seed statistics is scenario x seed (common random numbers).
    cells = [c for _, ds in per_seed for c in (ds.get("cells") or [])]
    base["cells"] = cells
    base["stats"] = stats_by_n(cells) if cells else None
    paired = _paired(per_seed, ns, pair)
    if paired:
        base["paired"] = paired
    return base


def merge_seed_datasets(existing: dict, new_per_seed, arms, ns, pair) -> dict:
    """Add new per-seed datasets to an already-aggregated `existing` dataset and
    re-aggregate, without re-running the seeds `existing` already covers."""
    old_seeds = existing.get("seeds") or [existing.get("seed", 0)]
    add = [(s, ds) for s, ds in new_per_seed if s not in old_seeds]
    if not add:
        return existing
    all_seeds = list(old_seeds) + [s for s, _ in add]
    n_old = len(old_seeds)

    # Rebuild value columns from the existing point _values (or the single-seed
    # scalar) plus the new seeds, then re-aggregate.
    cols = {arm: {n: {} for n in ns} for arm in arms}
    old_pts = {arm: {p["N"]: p for p in existing["arms"].get(arm, [])} for arm in arms}
    for arm in arms:
        for n in ns:
            op = old_pts[arm].get(n, {})
            for field in _AGG_FIELDS:
                prior = op.get(f"{field}_values")
                if prior is None:
                    v = op.get(field)
                    prior = [] if v is None else [v] * n_old
                vals = list(prior)
                for _, ds in add:
                    p = _seed_points(ds, arm).get(n, {})
                    if field in p and p[field] is not None:
                        vals.append(p[field])
                if vals:
                    cols[arm][n][field] = vals

    base = dict(existing)
    base["arms"] = _aggregate_arm_points(arms, ns, cols, len(all_seeds))

    # Paired: prior per-seed diffs + the new seeds' diffs.
    a, b = pair
    old_paired = (existing.get("paired") or {}).get(f"{a}_vs_{b}")
    new_paired = (_paired(add, ns, pair) or {}).get(f"{a}_vs_{b}")
    if old_paired is not None or new_paired is not None:
        old_by_n = {e["N"]: e for e in (old_paired or [])}
        new_by_n = {e["N"]: e for e in (new_paired or [])}
        merged = []
        for n in ns:
            vals = list(old_by_n.get(n, {}).get("values", [])) + list(new_by_n.get(n, {}).get("values", []))
            if vals:
                s = summarize(vals)
                merged.append({"N": n, "diff_mean": s["mean"], "diff_ci": s["ci"],
                               "diff_std": s["std"], "n": s["n"], "values": s["values"]})
        if merged:
            base["paired"] = {f"{a}_vs_{b}": merged}

    base["per_scenario"] = _merge_per_scenario(existing.get("per_scenario", {}), add, arms, n_old)
    base["errors"] = list(existing.get("errors", [])) + [e for _, ds in add for e in ds["errors"]]
    base["seeds"] = all_seeds
    base["n_seeds"] = len(all_seeds)
    # Per-cell records: only a dataset that carries them can extend them. A
    # legacy dataset (fractions only) cannot reconstruct booleans, so the
    # merged stats are honestly absent rather than approximated.
    old_cells = existing.get("cells")
    if old_cells is not None:
        cells = list(old_cells) + [c for _, ds in add for c in (ds.get("cells") or [])]
        base["cells"] = cells
        base["stats"] = stats_by_n(cells) if cells else None
    else:
        base["cells"] = None
        base["stats"] = None
    return base


def _merge_per_scenario(old_ps, add, arms, n_old) -> dict:
    """Combine existing per-scenario fractions (carrying their own n_seeds) with
    the new seeds' boolean records, by count-weighted averaging."""
    out = {}
    new_first = add[0][1]["per_scenario"] if add else {}
    for arm in arms:
        out[arm] = {}
        sids = set(old_ps.get(arm, {})) | set(new_first.get(arm, {}))
        for sid in sids:
            old_recs = {r["N"]: r for r in old_ps.get(arm, {}).get(sid, [])}
            new_by_n = {}
            for _, ds in add:
                for rec in ds["per_scenario"].get(arm, {}).get(sid, []):
                    new_by_n.setdefault(rec["N"], []).append(rec)
            recs = []
            for n in sorted(set(old_recs) | set(new_by_n)):
                o = old_recs.get(n)
                g = new_by_n.get(n, [])
                on = o.get("n_seeds", n_old) if o else 0
                tot = on + len(g)
                o_adh = float(o["adherent"]) if o else 0.0
                o_stale = float(o["stale_decision_followed"]) if o else 0.0
                adh = (o_adh * on + sum(1 for r in g if r["adherent"])) / tot if tot else 0.0
                stale = (o_stale * on + sum(1 for r in g if r["stale_decision_followed"])) / tot if tot else 0.0
                recs.append({"N": n, "adherent": adh, "stale_decision_followed": stale,
                             "governing_decision_retrieved": None, "n_seeds": tot})
            out[arm][sid] = recs
    return out


def _finite_adherence_points(pts: list[dict]) -> list[dict]:
    """Drop points with no adherence rate to plot — every cell at that (arm, N)
    hit the answering model's context window (see `_point`); there is no
    fake 0.0 to draw, and a gap in the line is the honest rendering."""
    return [p for p in pts if p.get("adherence_rate") is not None]


def render_chart(dataset: dict, out_path: str | Path) -> Path:
    """Render ONE crossover chart. matplotlib if present, else pure-Python SVG."""
    out_path = Path(out_path)
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=(7, 4.5))
        for arm, pts in dataset["arms"].items():
            pts = _finite_adherence_points(pts)
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
        pts = _finite_adherence_points(pts)
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
    atomic_write_text(data_path, json.dumps(dataset, indent=2))
    chart_path = render_chart(dataset, out_dir / "crossover")
    return data_path, chart_path
