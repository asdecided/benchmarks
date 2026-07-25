"""The autonomousqa harness CLI.

Subcommands:

- `apps`    — list the frozen sample apps and their seeded capabilities.
- `run`     — drive an agent over capabilities of one app and record results.
- `rescore` — re-derive verdicts and aggregates from recorded results.
              Deterministic; never spends a token.
- `report`  — render the results page (Markdown + HTML) from recorded results.
- `smoke`   — the CI-scale check: one cheap capability, scripted model,
              then prove the recording re-scores deterministically.

The corpus reaches the agent through the published `rac export --graph`
contract only; the reference agent through its published npm CLI only.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from agents import AGENTS
from runner.apps import APPS_ROOT, AppServer, list_apps, load_manifest
from runner.proxy import ModelProxy, load_flow
from runner.records import RESULTS_DIR, ReportWriter, build_record, load_reports
from scoring.aggregate import aggregate
from scoring.scorer import score_records
from scoring.report import write_report

MEMBER_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = MEMBER_ROOT / "workspace"
SMOKE_APP = "api-ledger"
SMOKE_CAPABILITY = "LEDGER-0000000000R1"


def export_graph(corpus: Path, out_path: Path) -> None:
    """Export the corpus graph over the published `rac export --graph` contract."""
    rac = os.environ.get("RAC_BIN", "decided")
    if shutil.which(rac) is None:
        raise FileNotFoundError(
            f"'{rac}' not on PATH — install asdecided-core or set RAC_BIN")
    result = subprocess.run([rac, "export", str(corpus), "--graph"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"rac export failed: {result.stderr.strip()}")
    out_path.write_text(result.stdout)


def run_one(app, capability, *, agent, mode: str, n: int,
            max_steps: int | None, model: str | None, workspace: Path,
            run_dir: Path) -> dict:
    """Drive one capability of one app; return the run record."""
    run_dir.mkdir(parents=True, exist_ok=True)
    graph_file = run_dir / "graph.json"
    export_graph(app.corpus, graph_file)

    with AppServer(app) as server:
        substitutions = {"base_url": server.base_url, "app_dir": str(app.dir)}
        if mode == "scripted":
            flow_path = app.flow_path(capability.id)
            if not flow_path.is_file():
                raise FileNotFoundError(
                    f"no scripted flow for {capability.id} at {flow_path} "
                    "(deliberately ambiguous capabilities have none)")
            proxy = ModelProxy("scripted",
                               flow=load_flow(flow_path, substitutions))
        else:
            proxy = ModelProxy(
                "forward",
                upstream_base_url=os.environ.get("OPENAI_BASE_URL"),
                upstream_api_key=os.environ.get("OPENAI_API_KEY"),
            )
        with proxy:
            from agents.base import RunSpec
            spec = RunSpec(
                app_name=app.name,
                modality=app.modality,
                capability_id=capability.id,
                graph_file=graph_file,
                start_url=server.start_url,
                base_url=server.base_url,
                workspace=workspace,
                # The compiled spec must land inside the workspace: the agent
                # runs its fidelity gate via `npx playwright test`, which only
                # collects tests under its own project root.
                out_dir=workspace / "generated" / run_dir.name,
                n=n,
                max_steps=max_steps,
                extension_dir=app.extension_dir,
                proxy_base_url=proxy.base_url,
                model=model or ("scripted" if mode == "scripted" else None),
            )
            invocation = agent.build(spec)
            env = {**os.environ, **invocation.env}
            started = time.monotonic()
            completed = subprocess.run(
                invocation.argv, cwd=invocation.cwd, env=env,
                capture_output=True, text=True, timeout=1800)
            wall_clock = time.monotonic() - started
            usage = proxy.usage_totals()

    outcome = agent.parse(completed.stdout, completed.returncode)
    return build_record(
        app=app, capability=capability,
        agent_name=agent.name, agent_version=agent.version(workspace),
        invocation_argv=invocation.argv, mode=mode,
        model=spec.model, n=n, max_steps=max_steps,
        outcome=outcome.as_dict(), usage=usage, wall_clock_s=wall_clock,
        stdout=completed.stdout, stderr=completed.stderr,
    )


def cmd_apps(_args) -> int:
    for app in list_apps():
        print(f"{app.name}  [{app.modality}]  frozen {app.frozen} — {app.summary}")
        for cap in app.capabilities:
            marks = [cap.tier] + (["negative"] if cap.negative else [])
            marks.append(f"expected {cap.expected}")
            print(f"  {cap.id}  ({', '.join(marks)})")
    return 0


def cmd_run(args) -> int:
    app = load_manifest(APPS_ROOT / args.app)
    agent = AGENTS[args.agent]
    if args.capability:
        capabilities = [app.capability(args.capability)]
    else:
        capabilities = [c for c in app.capabilities
                        if args.mode != "scripted" or app.flow_path(c.id).is_file()]
    writer = ReportWriter(args.label)
    failures = 0
    for capability in capabilities:
        for repeat in range(args.repeat):
            run_dir = (MEMBER_ROOT / "runs"
                       / f"{writer.stamp}-{capability.id}-{repeat}")
            record = run_one(
                app, capability, agent=agent, mode=args.mode, n=args.n,
                max_steps=args.max_steps, model=args.model,
                workspace=Path(args.workspace), run_dir=run_dir)
            writer.append(record)
            verdict = "verified" if record["outcome"]["verified"] else "unverified"
            print(f"{capability.id} [{repeat + 1}/{args.repeat}]: {verdict} "
                  f"({record['timing']['wall_clock_s']}s, "
                  f"{record['usage']['prompt_tokens']}/{record['usage']['completion_tokens']} tokens)")
            if not record["outcome"]["verified"]:
                failures += 1
    path = writer.finalize()
    print(f"wrote {path}")
    return 1 if failures and args.strict else 0


def cmd_rescore(args) -> int:
    records = load_reports([Path(p) for p in args.results])
    scores = score_records(records)
    print(json.dumps({"scores": scores, "aggregates": aggregate(scores)},
                     indent=2, sort_keys=True))
    return 0


def cmd_report(args) -> int:
    records = load_reports([Path(p) for p in args.results])
    scores = score_records(records)
    md_path, html_path = write_report(
        scores, aggregate(scores), Path(args.out), label=args.label)
    print(f"wrote {md_path}\nwrote {html_path}")
    return 0


def cmd_smoke(args) -> int:
    """One scripted capability, then prove the record re-scores deterministically."""
    app = load_manifest(APPS_ROOT / SMOKE_APP)
    capability = app.capability(SMOKE_CAPABILITY)
    agent = AGENTS["proofkeeper"]
    workspace = Path(args.workspace)
    writer = ReportWriter("smoke")
    run_dir = MEMBER_ROOT / "runs" / f"{writer.stamp}-smoke"
    record = run_one(app, capability, agent=agent, mode="scripted",
                     n=2, max_steps=8, model=None, workspace=workspace,
                     run_dir=run_dir)
    writer.append(record)
    path = writer.finalize()
    print(f"wrote {path}")

    if not record["outcome"]["verified"]:
        print("SMOKE FAIL: the scripted capability did not verify", file=sys.stderr)
        print(record["raw"]["stdout"], file=sys.stderr)
        print(record["raw"]["stderr_tail"], file=sys.stderr)
        return 1
    if record["usage"]["requests"] == 0:
        print("SMOKE FAIL: the drive never called the model proxy", file=sys.stderr)
        return 1

    records = load_reports([path])
    first = json.dumps({"scores": score_records(records),
                        "aggregates": aggregate(score_records(records))}, sort_keys=True)
    second = json.dumps({"scores": score_records(records),
                         "aggregates": aggregate(score_records(records))}, sort_keys=True)
    if first != second:
        print("SMOKE FAIL: re-scoring is not deterministic", file=sys.stderr)
        return 1
    rescored = score_records(records)[0]
    if not rescored["verified"]:
        print("SMOKE FAIL: re-score disagrees with the recorded outcome", file=sys.stderr)
        return 1
    print("SMOKE PASS: verified, metered, and re-scored deterministically")
    path.unlink()  # smoke artifacts are not results; keep the directory append-only
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="autonomousqa", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("apps", help="list sample apps and capabilities")

    run = sub.add_parser("run", help="drive an agent over an app's capabilities")
    run.add_argument("--app", required=True)
    run.add_argument("--capability", help="one capability id (default: all with expectations fitting the mode)")
    run.add_argument("--agent", default="proofkeeper", choices=sorted(AGENTS))
    run.add_argument("--mode", default="byok", choices=["byok", "scripted"])
    run.add_argument("--model", help="model name passed to the provider (byok mode)")
    run.add_argument("--n", type=int, default=3, help="fidelity re-runs (default 3)")
    run.add_argument("--max-steps", type=int, default=None)
    run.add_argument("--repeat", type=int, default=1, help="repeats per capability, for variance")
    run.add_argument("--label", default="local")
    run.add_argument("--workspace", default=str(WORKSPACE))
    run.add_argument("--strict", action="store_true", help="exit 1 if anything is unverified")

    rescore = sub.add_parser("rescore", help="re-derive verdicts from recorded results")
    rescore.add_argument("results", nargs="+")

    report = sub.add_parser("report", help="render the results page from recorded results")
    report.add_argument("results", nargs="+")
    report.add_argument("--out", default=str(RESULTS_DIR / "published"))
    report.add_argument("--label", default="results")

    smoke = sub.add_parser("smoke", help="CI-scale end-to-end check with the scripted model")
    smoke.add_argument("--workspace", default=str(WORKSPACE))

    args = parser.parse_args(argv)
    return {"apps": cmd_apps, "run": cmd_run, "rescore": cmd_rescore,
            "report": cmd_report, "smoke": cmd_smoke}[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
