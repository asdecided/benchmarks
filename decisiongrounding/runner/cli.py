"""decisiongrounding runner.

    python -m runner.cli run     --arm context_dump --scenarios scenarios/
    python -m runner.cli compare --arms context_dump,naive_rag --scenarios scenarios/
    python -m runner.cli demo    --scenarios scenarios/

`demo` is the one-command spine: it runs the two real arms on the worked
scenarios offline, writes an append-only report, and emits the crossover chart.

Reproducibility: the answering model + seed are pinned and recorded in every
RunResult. `results/` is append-only — runs are written as new timestamped
files and never mutated.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Make the package root importable when run as `python -m runner.cli` or directly.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from providers import (  # noqa: E402
    ARMS,
    REAL_ARMS,
    build_provider,
    make_answering_model,
)
from providers.answering import usage_dict  # noqa: E402
from providers.base import SCAFFOLD, ProposedChange  # noqa: E402
from scenarios.loader import Scenario, load_pool, load_scenarios  # noqa: E402
from scoring import aggregate, score  # noqa: E402
from scoring.crossover import (  # noqa: E402
    build_dataset,
    build_dataset_batched,
    build_dataset_multiseed,
    emit,
    merge_seed_datasets,
    run_seeds,
)

HARNESS_VERSION = "0.1.0-scaffold"
_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_RESULTS = _ROOT / "results"


def _answering_model(name: str, seed: int):
    # Thin CLI wrapper: surface the factory's error as a usage exit.
    try:
        return make_answering_model(name, seed)
    except ValueError as e:
        raise SystemExit(str(e))


def _provider(arm: str, model, embedder_spec: str):
    """Instantiate an arm, wiring a real embedder into naive_rag when asked."""
    return build_provider(arm, model, embedder_spec)


def _pc_to_dict(pc: ProposedChange) -> dict:
    return {
        "summary": pc.summary,
        "actions": [{"kind": a.kind, "target": a.target, "detail": a.detail} for a in pc.actions],
        "cites_decisions": list(pc.cites_decisions),
        "asserts_prohibition": pc.asserts_prohibition,
        "asserts_permission": pc.asserts_permission,
    }


def run_one(arm: str, scenario: Scenario, model, seed: int, embedder: str = "local-hash") -> dict:
    provider = _provider(arm, model, embedder)
    provider.prepare(list(scenario.corpus))
    pc = provider.respond(scenario.task)
    sc = score(scenario, pc)
    g = provider.grounding
    gov = scenario.gold_label.governing_decision
    governing_retrieved = None if gov is None else (gov in g.artifacts_supplied)
    # Reproducibility: record the embedder identity for retrieval arms (the dim
    # is probed during prepare()); null for arms that don't embed.
    emb = getattr(provider, "embedder", None)
    embedder_meta = {"name": emb.name, "dim": emb.dim} if emb is not None else None
    return {
        "run_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "arm": arm,
        "scenario_id": scenario.scenario_id,
        "corpus_size_N": len(scenario.corpus),
        "answering_model": {
            "name": model.name,
            "version": model.version,
            "temperature": model.temperature,
            "seed": seed,
        },
        "grounding": {
            "provider": arm,
            "token_estimate": g.token_estimate,
            "artifacts_supplied": list(g.artifacts_supplied),
        },
        "embedder": embedder_meta,
        # Real per-cell token usage when the answering model reports it (the
        # claude arm); None for the offline stub. Drives the cost report.
        "usage": getattr(model, "last_usage", None),
        "proposed_change": _pc_to_dict(pc),
        "score": sc.as_dict(),
        "retrieval": {"governing_decision_retrieved": governing_retrieved},
        "harness_version": HARNESS_VERSION,
    }


def _preflight(arms: tuple[str, ...], answering: str, embedder: str) -> None:
    """Fail fast — BEFORE any work or API spend — if the requested configuration
    cannot run. A real run is expensive; surfacing a missing key or package up
    front beats discovering it mid-sweep after burning credits."""
    problems: list[str] = []

    if answering == "claude":
        if importlib.util.find_spec("anthropic") is None:
            problems.append("--answering claude needs `anthropic` (pip install -e '.[real]')")
        elif not os.environ.get("ANTHROPIC_API_KEY"):
            problems.append("--answering claude needs ANTHROPIC_API_KEY in the environment")

    if "naive_rag" in arms:
        if embedder.startswith("voyage"):
            if importlib.util.find_spec("voyageai") is None:
                problems.append("--embedder voyage needs `voyageai` (pip install -e '.[real]')")
            elif not os.environ.get("VOYAGE_API_KEY"):
                problems.append("--embedder voyage needs VOYAGE_API_KEY in the environment")
        elif embedder.startswith("st") and importlib.util.find_spec("sentence_transformers") is None:
            problems.append("--embedder st needs `sentence-transformers` (pip install -e '.[local-embeddings]')")

    if "rac" in arms and shutil.which(os.environ.get("RAC_BIN", "rac")) is None:
        problems.append(
            "the rac arm needs the `rac` CLI on PATH (pip install -e the rac repo, or set RAC_BIN)"
        )

    if problems:
        raise SystemExit("preflight failed:\n" + "\n".join(f"  - {p}" for p in problems))


def _execute_runs(
    pairs: list[tuple[str, Scenario]],
    model,
    seed: int,
    embedder: str,
    partial_path: Path,
) -> tuple[list[dict], list[dict]]:
    """Run each (arm, scenario) cell, streaming every completed RunResult to a
    durable `.partial.jsonl` sidecar as it lands. A crash or API error on one
    cell is recorded and skipped — it never discards the cells already done, so a
    long paid run preserves every result it managed to produce."""
    results: list[dict] = []
    errors: list[dict] = []
    partial_path.parent.mkdir(parents=True, exist_ok=True)
    with partial_path.open("a", encoding="utf-8") as fp:
        for arm, sc in pairs:
            try:
                r = run_one(arm, sc, model, seed, embedder)
            except Exception as exc:  # noqa: BLE001 - one cell must not kill the batch
                err = {"arm": arm, "scenario_id": sc.scenario_id, "error": repr(exc)}
                errors.append(err)
                fp.write(json.dumps({"record": "error", **err}) + "\n")
                fp.flush()
                print(f"  ! {arm}/{sc.scenario_id} failed, continuing: {exc}", file=sys.stderr)
                continue
            results.append(r)
            fp.write(json.dumps({"record": "run", **r}) + "\n")
            fp.flush()
    return results, errors


def _backend_versions() -> dict:
    """Best-effort: the installed versions of the real backends, so each report
    records exactly what produced it. Empty when the [real] extra isn't present."""
    import importlib.metadata as md

    out: dict[str, str] = {}
    for pkg in ("anthropic", "voyageai"):
        try:
            out[pkg] = md.version(pkg)
        except Exception:  # noqa: BLE001 - absence is expected offline
            pass
    return out


def _write_report(
    results: list[dict],
    out_dir: Path,
    label: str,
    errors: list[dict] | None = None,
    stamp: str | None = None,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"run-{stamp}-{label}.json"
    if path.exists():  # append-only: never overwrite an existing run file
        path = out_dir / f"run-{stamp}-{label}-{uuid.uuid4().hex[:6]}.json"
    by_arm: dict[str, list] = {}
    for r in results:
        by_arm.setdefault(r["arm"], []).append(r)
    from scoring.scorer import Score

    metrics = {
        arm: aggregate(
            arm,
            [Score(**r["score"]) for r in rs],
            [r["retrieval"]["governing_decision_retrieved"] for r in rs],
        ).as_dict()
        for arm, rs in by_arm.items()
    }
    report = {
        "harness_version": HARNESS_VERSION,
        "generated": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "backend_versions": _backend_versions(),
        "metrics_by_arm": metrics,
        "runs": results,
        "errors": errors or [],
    }
    path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return path


def _print_metrics(results: list[dict]) -> None:
    by_arm: dict[str, list] = {}
    for r in results:
        by_arm.setdefault(r["arm"], []).append(r)
    from scoring.scorer import Score

    print(f"{'arm':<16}{'adhere':>8}{'stale':>8}{'f-permit':>10}{'f-prohibit':>12}{'gov-recall':>12}")
    for arm, rs in by_arm.items():
        m = aggregate(
            arm,
            [Score(**r["score"]) for r in rs],
            [r["retrieval"]["governing_decision_retrieved"] for r in rs],
        )
        recall = "  n/a" if m.governing_recall_rate is None else f"{m.governing_recall_rate:.2f}"
        print(
            f"{arm:<16}{m.adherence_rate:>8.2f}{m.stale_decision_rate:>8.2f}"
            f"{m.false_permit_rate:>10.2f}{m.false_prohibit_rate:>12.2f}{recall:>12}"
        )


def cmd_run(args) -> int:
    _preflight((args.arm,), args.answering, args.embedder)
    scenarios = load_scenarios(args.scenarios)
    model = _answering_model(args.answering, args.seed)
    out_dir = Path(args.out)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    partial = out_dir / f"run-{stamp}-{args.arm}.partial.jsonl"
    pairs = [(args.arm, sc) for sc in scenarios]
    results, errors = _execute_runs(pairs, model, args.seed, args.embedder, partial)
    _print_metrics(results)
    path = _write_report(results, out_dir, args.arm, errors, stamp)
    print(f"\nwrote {path}")
    return 1 if errors else 0


def cmd_compare(args) -> int:
    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    _preflight(arms, args.answering, args.embedder)
    scenarios = load_scenarios(args.scenarios)
    model = _answering_model(args.answering, args.seed)
    out_dir = Path(args.out)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = "compare-" + "-".join(arms)
    partial = out_dir / f"run-{stamp}-{label}.partial.jsonl"
    pairs = [(arm, sc) for arm in arms for sc in scenarios]
    results, errors = _execute_runs(pairs, model, args.seed, args.embedder, partial)
    _print_metrics(results)
    path = _write_report(results, out_dir, label, errors, stamp)
    print(f"\nwrote {path}")
    return 1 if errors else 0


def cmd_batch(args) -> int:
    """Same comparison as `compare`, but the answering calls go through the
    Message Batches API at 50% of standard price. Grounding assembly (rac CLI,
    embeddings) still runs locally up front; only the held-constant answering
    model is batched. Asynchronous: submit one batch, poll, then score."""
    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    if args.answering != "claude":
        raise SystemExit(
            "batch mode requires --answering claude (the Batch API discounts the "
            "pinned answering model; the offline stub has nothing to batch)."
        )
    _preflight(arms, args.answering, args.embedder)
    scenarios = load_scenarios(args.scenarios)
    model = _answering_model("claude", args.seed)
    out_dir = Path(args.out)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    label = "batch-" + "-".join(arms)

    # 1. Assemble every cell's grounding + request locally (rac CLI / embeddings
    #    happen here). The answering calls are submitted together below.
    cells: list[dict] = []
    for arm in arms:
        for sc in scenarios:
            provider = _provider(arm, model, args.embedder)
            provider.prepare(list(sc.corpus))
            grounding = provider.assemble(sc.task)
            gov = sc.gold_label.governing_decision
            emb = getattr(provider, "embedder", None)
            skel = {
                "run_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "arm": arm,
                "scenario_id": sc.scenario_id,
                "corpus_size_N": len(sc.corpus),
                "answering_model": {
                    "name": model.name, "version": model.version,
                    "temperature": model.temperature, "seed": args.seed,
                },
                "grounding": {
                    "provider": arm, "token_estimate": grounding.token_estimate,
                    "artifacts_supplied": list(grounding.artifacts_supplied),
                },
                "embedder": ({"name": emb.name, "dim": emb.dim} if emb is not None else None),
                "retrieval": {
                    "governing_decision_retrieved": (
                        None if gov is None else (gov in grounding.artifacts_supplied)
                    )
                },
                "harness_version": HARNESS_VERSION,
            }
            cells.append({
                "custom_id": f"c{len(cells)}",
                "params": model.build_request(SCAFFOLD, grounding, sc.task),
                "scenario": sc,
                "skel": skel,
            })

    # 2. Submit one batch (50% of standard token price).
    client = model._ensure_client()
    requests = [{"custom_id": c["custom_id"], "params": c["params"]} for c in cells]
    batch = client.messages.batches.create(requests=requests)
    print(f"submitted batch {batch.id}: {len(requests)} requests "
          f"({len(arms)} arms x {len(scenarios)} scenarios) at Batch-API pricing (~50% off)")

    # 3. Poll until the batch ends (usually < 1h; max 24h).
    while True:
        b = client.messages.batches.retrieve(batch.id)
        if b.processing_status == "ended":
            break
        rc = getattr(b, "request_counts", None)
        if rc is not None:
            print(f"  {b.processing_status}: processing={rc.processing} "
                  f"succeeded={rc.succeeded} errored={rc.errored}")
        time.sleep(max(5, args.poll))

    # 4. Collect results by custom_id, parse + score. Results arrive in any order.
    by_cid = {c["custom_id"]: c for c in cells}
    results: list[dict] = []
    errors: list[dict] = []
    for r in client.messages.batches.results(batch.id):
        cell = by_cid.get(r.custom_id)
        if cell is None:
            continue
        arm, sid = cell["skel"]["arm"], cell["skel"]["scenario_id"]
        if r.result.type != "succeeded":
            errors.append({"arm": arm, "scenario_id": sid, "error": f"batch result: {r.result.type}"})
            continue
        try:
            pc = model.parse_message(r.result.message)
        except Exception as exc:  # noqa: BLE001 - one cell must not lose the batch
            errors.append({"arm": arm, "scenario_id": sid, "error": repr(exc)})
            continue
        run = dict(cell["skel"])
        run["usage"] = usage_dict(getattr(r.result.message, "usage", None))
        run["proposed_change"] = _pc_to_dict(pc)
        run["score"] = score(cell["scenario"], pc).as_dict()
        results.append(run)

    _print_metrics(results)
    path = _write_report(results, out_dir, label, errors, stamp)
    print(f"\nwrote {path}")
    return 1 if errors else 0


def _parse_seeds(spec) -> list[int] | None:
    """Parse a --seeds spec into a sorted, unique int list, or None if unset.

    Accepts "3" (seed 3 only), "0,1,2", "0-4" (range, inclusive), and combos like
    "0-2,5". A single value is one seed, not a count.
    """
    if not spec:
        return None
    out: list[int] = []
    for part in str(spec).split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part.lstrip("-"):  # a range like 0-4 (not a bare negative)
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return sorted(dict.fromkeys(out))


def _fmt_pt(p: dict, field: str) -> str:
    """Format a curve point's field as `mean` or `mean±half` (multi-seed)."""
    v = p.get(field)
    if v is None:
        return "n/a"
    ci = p.get(f"{field}_ci")
    if ci and p.get("n_seeds", 1) > 1:
        return f"{v:.2f}±{(ci[1] - ci[0]) / 2:.2f}"
    return f"{v:.2f}"


def _fmt_adherent(v) -> str:
    """Per-scenario adherence cell: 1/0 for a single seed, a fraction otherwise."""
    if isinstance(v, bool):
        return "1" if v else "0"
    return f"{v:.1f}"


def cmd_demo(args) -> int:
    arms = tuple(a.strip() for a in args.arms.split(",") if a.strip())
    _preflight(arms, args.answering, args.embedder)
    scenarios = load_scenarios(args.scenarios)
    ns = tuple(int(x) for x in args.ns.split(",") if x.strip())
    if args.answering == "claude":
        print(
            f"NOTE: --answering claude makes real API calls "
            f"(~ {len(arms)} arms x scenarios x {len(ns)} corpus sizes). "
            f"Use --ns to keep a real run cheap (e.g. --ns 10,50).\n"
        )
    model = _answering_model(args.answering, args.seed)
    out_dir = Path(args.out)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    print("== per-scenario, per-arm (tiny corpus) ==")
    partial = out_dir / f"run-{stamp}-demo.partial.jsonl"
    pairs = [(arm, sc) for arm in arms for sc in scenarios]
    results, errors = _execute_runs(pairs, model, args.seed, args.embedder, partial)
    _print_metrics(results)
    report = _write_report(results, out_dir, "demo", errors, stamp)

    pool = None
    if args.distractors == "real":
        pool = load_pool(args.pool)
        print(
            f"\n(real distractors: {len(pool)} public PEP decisions from {args.pool})"
        )
    print("\n== adherence vs corpus size (discriminating scenarios, averaged) ==")
    # Stream every completed cell to a durable sidecar AND print a live progress
    # line, so a long real sweep is observable and never lost mid-run.
    sweep_partial = out_dir / f"run-{stamp}-crossover.partial.jsonl"
    sweep_partial.parent.mkdir(parents=True, exist_ok=True)
    _t0 = time.time()
    _sweep_fp = sweep_partial.open("a", encoding="utf-8")

    def _on_cell(rec: dict) -> None:
        _sweep_fp.write(json.dumps(rec) + "\n")
        _sweep_fp.flush()
        done, total = rec["idx"], rec["total"]
        elapsed = time.time() - _t0
        eta = (elapsed / done) * (total - done) if done else 0
        flag = "ERR" if rec.get("error") else ("adhere" if rec["adherent"] else "miss")
        print(
            f"  [{done:>3}/{total}] {done * 100 // total:>3}%  N={rec['N']:<4} "
            f"{rec['arm']:<13}{rec['scenario_id']:<34} {flag:<6} "
            f"eta {eta/60:4.1f}m",
            file=sys.stderr,
        )

    pool_dir = args.pool if args.distractors == "real" else None
    seeds = _parse_seeds(getattr(args, "seeds", None))
    augment = getattr(args, "augment", None)
    batch = bool(getattr(args, "batch", False))
    if batch and args.answering != "claude":
        _sweep_fp.close()
        raise SystemExit("--batch requires --answering claude (the Batch API "
                         "discounts the pinned model; the offline stub has nothing to batch)")
    if batch:
        print("  (Batch API: assembling cells locally, then one batch per seed at ~50% price)",
              file=sys.stderr)
    try:
        if augment:
            existing = json.loads(Path(augment).read_text(encoding="utf-8"))
            have = set(existing.get("seeds") or [existing.get("seed", 0)])
            want = seeds if seeds is not None else sorted(have)
            todo = [s for s in want if s not in have]
            if not todo:
                print("  (augment: no new seeds to run; re-emitting)", file=sys.stderr)
                dataset = existing
            else:
                print(f"  (augment: {sorted(have)} + new {todo})", file=sys.stderr)
                new_ps = run_seeds(
                    scenarios, arms, ns, todo,
                    answering_model_name=args.answering, embedder_spec=args.embedder,
                    pool=pool, pool_dir=pool_dir, scenarios_dir=args.scenarios,
                    batched=batch, poll=args.poll, progress=_on_cell)
                dataset = merge_seed_datasets(existing, new_ps, list(arms), list(ns),
                                              ("rac", "naive_rag"))
        elif seeds is not None:
            if len(seeds) > 1:
                print(f"  (multi-seed: {seeds}; reporting mean +/- 95% CI)", file=sys.stderr)
            dataset = build_dataset_multiseed(
                scenarios, arms=arms, ns=ns, seeds=seeds,
                answering_model_name=args.answering, embedder_spec=args.embedder,
                pool=pool, pool_dir=pool_dir, scenarios_dir=args.scenarios,
                batched=batch, poll=args.poll, pair=("rac", "naive_rag"), progress=_on_cell)
        elif batch:
            dataset = build_dataset_batched(
                scenarios, arms=arms, ns=ns, seed=args.seed, embedder_spec=args.embedder,
                pool=pool, pool_dir=pool_dir, scenarios_dir=args.scenarios,
                poll=args.poll, progress=_on_cell,
            )
        else:
            dataset = build_dataset(
                scenarios, arms=arms, ns=ns, seed=args.seed,
                answering_model_name=args.answering, embedder_spec=args.embedder,
                pool=pool, pool_dir=pool_dir, scenarios_dir=args.scenarios,
                progress=_on_cell,
            )
    finally:
        _sweep_fp.close()
    multiseed = dataset.get("n_seeds", 1) > 1
    for arm in arms:
        row = " ".join(f"N={p['N']}:{_fmt_pt(p, 'adherence_rate')}" for p in dataset["arms"][arm])
        print(f"{arm:<16}{row}")
    print("\n== governing-decision recall vs corpus size (why adherence moves) ==")
    for arm in arms:
        row = " ".join(f"N={p['N']}:{_fmt_pt(p, 'governing_recall')}" for p in dataset["arms"][arm])
        print(f"{arm:<16}{row}")

    if multiseed and "paired" in dataset:
        print("\n== rac - naive_rag adherence (paired across seeds; the falsifier statistic) ==")
        for e in dataset["paired"].get("rac_vs_naive_rag", []):
            lo, hi = e["diff_ci"]
            verdict = "rac>" if lo > 0 else ("tie/loss" if hi >= 0 else "rac<")
            print(f"  N={e['N']:<4} diff={e['diff_mean']:+.2f}  95% CI [{lo:+.2f}, {hi:+.2f}]  {verdict}")

    print("\n== per-scenario adherence (where the average comes from) ==")
    for arm in arms:
        for sid, series in dataset["per_scenario"][arm].items():
            row = " ".join(f"N={p['N']}:{_fmt_adherent(p['adherent'])}" for p in series)
            print(f"{arm:<13}{sid:<32}{row}")
    data_path, chart_path = emit(dataset, out_dir)
    print(f"\nwrote {report}\nwrote {data_path}\nwrote {chart_path}")
    if args.answering == "offline-stub":
        print(
            "\nNOTE: offline-stub output is a harness illustration, NOT a benchmark "
            "result. See README and ADR-0001."
        )
    else:
        print(
            "\nNOTE: real-model run on the tiny SYNTHETIC scenarios — a real-model "
            "crossover, not yet the real-CORPUS evidence run. See README and ADR-0001."
        )
    return 0


def cmd_ui(args) -> int:
    """Serve the local results dashboard. FastAPI + uvicorn are an optional
    extra; surface a clear install hint if they are missing."""
    from runner.ui import UIUnavailable, run_ui

    try:
        run_ui(results_dir=args.results, host=args.host, port=args.port, template=args.template)
    except UIUnavailable as exc:
        raise SystemExit(str(exc))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="decisiongrounding", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    common = dict()
    for name in ("run", "compare", "demo", "batch"):
        sp = sub.add_parser(name)
        sp.add_argument("--scenarios", default=str(_ROOT / "scenarios"))
        sp.add_argument("--out", default=str(_DEFAULT_RESULTS))
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument(
            "--answering",
            default="offline-stub",
            help="offline-stub | claude | litellm:<model-alias> "
            "(OpenAI-compatible gateway; needs LITELLM_BASE_URL + LITELLM_API_KEY)",
        )
        sp.add_argument(
            "--embedder",
            default="local-hash",
            help="naive_rag embedder: local-hash (offline) | voyage[:model] | st[:model]",
        )
        if name == "run":
            sp.add_argument("--arm", required=True, choices=sorted(ARMS))
        if name == "compare":
            sp.add_argument("--arms", default=",".join(REAL_ARMS))
        if name == "batch":
            sp.add_argument("--arms", default="context_dump,naive_rag,no_grounding,rac")
            sp.add_argument(
                "--poll", type=int, default=20,
                help="seconds between Batch-API status polls",
            )
        if name == "demo":
            sp.add_argument("--arms", default=",".join(REAL_ARMS))
            sp.add_argument(
                "--ns",
                default="10,50,150,300",
                help="comma-separated corpus sizes for the crossover sweep "
                "(smaller keeps a real run cheap, e.g. 10,50)",
            )
            sp.add_argument(
                "--distractors",
                default="synthetic",
                choices=["synthetic", "real"],
                help="N-curve padding: synthetic `note` filler (illustrative) or "
                "real public PEP decisions from a built pool (the honest curve)",
            )
            sp.add_argument(
                "--pool",
                default=str(_ROOT / "scenarios_real" / "peps_pool"),
                help="real distractor pool dir (build: python -m ingest.peps pool build)",
            )
            sp.add_argument(
                "--batch", action="store_true",
                help="run the sweep's answering calls via the Batch API "
                "(~50%% price, survives restarts; requires --answering claude)",
            )
            sp.add_argument(
                "--poll", type=int, default=20,
                help="seconds between Batch-API status polls (with --batch)",
            )
            sp.add_argument(
                "--seeds", default=None,
                help="run the sweep over several seeds and report mean +/- 95%% CI "
                "(spec: '0-4' | '0,1,2' | '0-2,5'; a single '3' = seed 3 only). "
                "Cost multiplies with the number of seeds.",
            )
            sp.add_argument(
                "--augment", default=None,
                help="path to an existing crossover_dataset.json: run only the "
                "--seeds not already in it and merge (append-friendly, no re-run)",
            )

    # The local web UI is a different shape (no scenarios/answering knobs).
    sp_ui = sub.add_parser("ui", help="serve the local results dashboard (needs the [ui] extra)")
    sp_ui.add_argument("--results", default=str(_DEFAULT_RESULTS / "published"),
                       help="directory to read the latest run + crossover from")
    sp_ui.add_argument("--host", default="127.0.0.1")
    sp_ui.add_argument("--port", type=int, default=8099)
    sp_ui.add_argument("--template", default=None,
                       help="path to a custom dashboard HTML template (else DG_UI_TEMPLATE or the default)")

    args = p.parse_args(argv)
    return {
        "run": cmd_run, "compare": cmd_compare, "demo": cmd_demo,
        "batch": cmd_batch, "ui": cmd_ui,
    }[args.cmd](args)


if __name__ == "__main__":
    raise SystemExit(main())
