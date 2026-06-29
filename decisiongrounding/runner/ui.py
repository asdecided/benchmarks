"""Local web UI for the benchmark — the `decisiongrounding ui` command.

A localhost console to inspect a run interactively: the leaderboard, the
adherence/recall/cost-vs-N curves, the rac-vs-naive_rag head-to-head, and a
per-scenario failure drill-down. Same spirit as the rest of the repo: FastAPI +
uvicorn are an OPTIONAL extra, imported lazily so the core stays dependency-free
(`pip install -e '.[ui]'`). The page itself is rendered by `runner.dashboard`
(one self-contained HTML string — no static assets, no frontend build).

The server reads the latest results from a directory on every request, so a run
that finishes while the UI is open shows up on refresh.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

from runner.dashboard import build_dashboard, curve_from_dataset, render_main
from scoring.cost import dollars

_ROOT = Path(__file__).resolve().parent.parent
_GBP = 0.79  # rough USD -> GBP, for the confirmation estimate only
_KNOWN_ARMS = {"context_dump", "naive_rag", "no_grounding", "rac"}


class UIUnavailable(RuntimeError):
    """Raised when the optional UI extra (fastapi + uvicorn) is not installed."""


def paid_enabled() -> bool:
    """Real (paid) runs are gated behind an explicit opt-in env flag, so a web
    button can never spend money unless the operator started the server with it."""
    return os.environ.get("DG_UI_ALLOW_PAID", "") not in ("", "0", "false", "False")


def _require_ui():
    try:
        import fastapi  # noqa: F401
        import uvicorn  # noqa: F401
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise UIUnavailable(
            "the UI needs its extra: pip install -e '.[ui]'"
        ) from exc


def _latest(results_dir: Path, *patterns: str) -> Path | None:
    """Newest file in results_dir matching any glob, or None."""
    hits = [p for pat in patterns for p in results_dir.glob(pat)]
    return max(hits, key=lambda p: p.stat().st_mtime) if hits else None


def load_results(results_dir: str | Path) -> tuple[dict | None, dict | None]:
    """(run, crossover_dataset) — the newest of each found under results_dir.
    Either may be None when nothing has been produced yet."""
    d = Path(results_dir)
    run_path = _latest(d, "*headline*.json", "run-*-compare-*.json", "run-*-batch-*.json", "run-*-demo.json")
    ds_path = _latest(d, "crossover_dataset.json", "*crossover*dataset*.json")
    run = json.loads(run_path.read_text()) if run_path else None
    dataset = json.loads(ds_path.read_text()) if ds_path else None
    return run, dataset


# --- triggering a run from the UI -----------------------------------------
#
# One run at a time. The server builds the argv itself from a small whitelist
# (mode/command/arms/ns/batch) and execs the existing CLI with no shell — the
# client never supplies a command string. Offline runs are free and always
# allowed; real (paid) runs require paid_enabled().

_RUN_LOCK = threading.RLock()  # reentrant: start_run() calls run_status() while held
_RUN: dict = {"state": "idle"}  # state: idle|running|done|error


def _clean_arms(arms) -> list[str]:
    out = [a for a in (arms or []) if a in _KNOWN_ARMS]
    return out or ["context_dump", "naive_rag", "no_grounding", "rac"]


def _clean_ns(ns) -> list[int]:
    try:
        vals = sorted({int(n) for n in ns if int(n) > 0})
    except (TypeError, ValueError):
        vals = []
    return vals or [10, 50]


def estimate_cost(results_dir, command: str, arms: list[str], ns: list[int], batch: bool) -> dict:
    """Rough £/$ estimate for a real run, from the latest run's recorded per-arm
    grounding token sizes. Clearly an estimate (±~30%); offline runs are free."""
    run, _ = load_results(results_dir)
    per_arm, n_scen = {}, 19
    if run and run.get("runs"):
        by: dict[str, list[int]] = {}
        for r in run["runs"]:
            by.setdefault(r["arm"], []).append((r.get("grounding") or {}).get("token_estimate", 0))
        per_arm = {a: (sum(v) / len(v)) for a, v in by.items()}
        n_scen = len({r["scenario_id"] for r in run["runs"]})
    default_in = 30000  # fallback when an arm has no recorded size yet
    out_tok = 150
    cells = 0
    usd = 0.0
    for a in arms:
        tin = per_arm.get(a, default_in)
        reps = n_scen + (n_scen * len(ns) if command == "crossover" else 0)
        cells += reps
        usd += reps * dollars(int(tin) + 400, out_tok, "claude-opus-4-8", batch=batch)
    return {"command": command, "arms": arms, "ns": ns, "batch": batch,
            "calls": cells, "usd": round(usd, 2), "gbp": round(usd * _GBP, 2),
            "note": "estimate ±~30% from recorded token sizes"}


def _argv_for(mode: str, command: str, arms: list[str], ns: list[int], batch: bool, results_dir: Path) -> tuple[list[str], int]:
    """Build the CLI argv and the expected cell total. Real runs use the pinned
    Claude model + Voyage; offline runs use the free stubs."""
    base = [sys.executable, "-m", "runner.cli"]
    common = ["--scenarios", str(_ROOT / "scenarios_real"), "--out", str(results_dir),
              "--arms", ",".join(arms)]
    if mode == "real":
        backend = ["--answering", "claude", "--embedder", "voyage:voyage-4-large"]
    else:
        backend = ["--answering", "offline-stub", "--embedder", "local-hash"]
    if command == "crossover":
        argv = base + ["demo", *common, *backend, "--ns", ",".join(map(str, ns)),
                       "--distractors", "real" if mode == "real" else "synthetic",
                       "--pool", str(_ROOT / "scenarios_real" / "peps_pool")]
        total = len(arms) * 19 * (1 + len(ns))  # base-N table + sweep
    else:  # compare (base-N headline)
        cmd = "batch" if (batch and mode == "real") else "compare"
        argv = base + [cmd, *common, *backend]
        total = len(arms) * 19
    return argv, total


def start_run(results_dir, *, mode: str, command: str, arms, ns, batch: bool, confirm_usd=None) -> dict:
    """Launch a run as a subprocess. Returns the new status. Raises ValueError on
    a guard violation (run in progress, paid not enabled, missing confirmation)."""
    arms, ns = _clean_arms(arms), _clean_ns(ns)
    command = command if command in ("compare", "crossover") else "compare"
    with _RUN_LOCK:
        if _RUN.get("state") == "running":
            raise ValueError("a run is already in progress")
        if mode == "real":
            if not paid_enabled():
                raise ValueError("real runs are disabled; start the server with DG_UI_ALLOW_PAID=1")
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise ValueError("real runs need ANTHROPIC_API_KEY in the server environment")
            est = estimate_cost(results_dir, command, arms, ns, batch)
            if confirm_usd is None or abs(float(confirm_usd) - est["usd"]) > 0.01:
                raise ValueError(f"cost confirmation required: re-send confirm_usd={est['usd']}")
        rd = Path(results_dir); rd.mkdir(parents=True, exist_ok=True)
        argv, total = _argv_for(mode, command, arms, ns, batch, rd)
        log = rd / f"ui-run-{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}.log"
        proc = subprocess.Popen(argv, cwd=str(_ROOT), stdout=log.open("w"),
                                stderr=subprocess.STDOUT)
        _RUN.clear()
        _RUN.update(state="running", mode=mode, command=command, arms=arms, ns=ns,
                    batch=batch, argv=argv, total=total, started=time.time(),
                    log=str(log), results_dir=str(rd), proc=proc)
        return run_status()


def _count_progress(results_dir: Path) -> tuple[int, dict | None]:
    """Cells completed so far, read from the newest per-cell sidecar."""
    sidecars = sorted(results_dir.glob("run-*-crossover.partial.jsonl"),
                      key=lambda p: p.stat().st_mtime)
    sidecars += sorted(results_dir.glob("run-*.partial.jsonl"), key=lambda p: p.stat().st_mtime)
    if not sidecars:
        return 0, None
    last = None
    done = 0
    for line in sidecars[-1].read_text().splitlines():
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        done += 1
        last = rec
    return done, last


def run_status() -> dict:
    """Current run state (safe to serialise — no Popen handle)."""
    with _RUN_LOCK:
        st = {k: v for k, v in _RUN.items() if k != "proc"}
        proc = _RUN.get("proc")
        if proc is not None and _RUN.get("state") == "running":
            rc = proc.poll()
            if rc is not None:
                _RUN["state"] = st["state"] = "done" if rc == 0 else "error"
                _RUN["returncode"] = st["returncode"] = rc
        if _RUN.get("results_dir"):
            done, last = _count_progress(Path(_RUN["results_dir"]))
            st["progress"] = {"done": done, "total": _RUN.get("total"),
                              "pct": int(done * 100 / _RUN["total"]) if _RUN.get("total") else None,
                              "last": last}
        if _RUN.get("log") and Path(_RUN["log"]).exists():
            st["log_tail"] = "\n".join(Path(_RUN["log"]).read_text().splitlines()[-12:])
    return st


_EMPTY = (
    "<!doctype html><meta charset=utf-8><title>Decision Grounding Bench</title>"
    "<body style='font-family:sans-serif;padding:40px;max-width:680px'>"
    "<h1>Decision Grounding Bench</h1>"
    "<p>No results found in <code>{dir}</code> yet.</p>"
    "<p>Produce some, then refresh:</p>"
    "<pre style='background:#f5f5f5;padding:14px;border-radius:8px'>"
    "make real-crossover   # needs ANTHROPIC_API_KEY (+ VOYAGE_API_KEY)\n"
    "make demo             # offline illustration, no key needed</pre></body>"
)


def build_ui_app(results_dir: str | Path = "results/published", template: str | Path | None = None):
    """Build the FastAPI app. Routes:
      GET /            -> the dashboard (re-rendered from the latest results)
      GET /healthz     -> liveness
      GET /api/run     -> latest run JSON
      GET /api/crossover -> latest crossover dataset JSON
      GET /api/cost-curve -> {arm: {N: tokens}} derived from the dataset
    """
    _require_ui()
    from fastapi import Body, FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    results_dir = Path(results_dir)
    app = FastAPI(title="Decision Grounding Bench", docs_url="/api/docs")

    @app.get("/", response_class=HTMLResponse)
    def index():  # noqa: ANN202
        run, dataset = load_results(results_dir)
        if run is None:
            return HTMLResponse(_EMPTY.format(dir=results_dir))
        return HTMLResponse(build_dashboard(run, dataset, live=True,
                                            paid_enabled=paid_enabled(), template=template))

    @app.get("/api/run/estimate")
    def api_estimate(command: str = "compare", arms: str = "", ns: str = "10,50", batch: bool = False):  # noqa: ANN202
        a = _clean_arms(arms.split(",") if arms else None)
        n = _clean_ns(ns.split(",") if ns else None)
        return estimate_cost(results_dir, command if command in ("compare", "crossover") else "compare", a, n, batch)

    @app.get("/api/run/status")
    def api_run_status():  # noqa: ANN202
        return run_status()

    @app.post("/api/run/start")
    def api_run_start(body: dict = Body(default={})):  # noqa: ANN202
        try:
            st = start_run(
                results_dir,
                mode=body.get("mode", "offline"),
                command=body.get("command", "compare"),
                arms=body.get("arms"),
                ns=body.get("ns"),
                batch=bool(body.get("batch", False)),
                confirm_usd=body.get("confirm_usd"),
            )
            return JSONResponse({"ok": True, **st})
        except ValueError as exc:
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @app.get("/api/fragment", response_class=HTMLResponse)
    def fragment():  # noqa: ANN202
        # The <main> inner, server-rendered from the latest results — the page
        # swaps this in place (no full reload) on refresh / run completion.
        run, dataset = load_results(results_dir)
        if run is None:
            return HTMLResponse("", status_code=204)
        return HTMLResponse(render_main(run, dataset, live=True, paid_enabled=paid_enabled()))

    @app.get("/healthz")
    def healthz():  # noqa: ANN202
        run, _ = load_results(results_dir)
        return {"ok": True, "has_run": run is not None, "results_dir": str(results_dir)}

    @app.get("/api/run")
    def api_run():  # noqa: ANN202
        run, _ = load_results(results_dir)
        return JSONResponse(run or {}, status_code=200 if run else 404)

    @app.get("/api/crossover")
    def api_crossover():  # noqa: ANN202
        _, dataset = load_results(results_dir)
        return JSONResponse(dataset or {}, status_code=200 if dataset else 404)

    @app.get("/api/cost-curve")
    def api_cost_curve():  # noqa: ANN202
        _, dataset = load_results(results_dir)
        return JSONResponse(curve_from_dataset(dataset) or {})

    return app


def run_ui(results_dir: str | Path = "results/published", host: str = "127.0.0.1",
           port: int = 8099, template: str | Path | None = None) -> None:
    """Serve the UI with uvicorn (the `decisiongrounding ui` command)."""
    _require_ui()
    import uvicorn

    app = build_ui_app(results_dir, template=template)
    print(f"Decision Grounding Bench UI -> http://{host}:{port}  (results: {results_dir})")
    uvicorn.run(app, host=host, port=port, log_level="warning")
