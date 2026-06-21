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
from pathlib import Path

from runner.dashboard import build_dashboard, curve_from_dataset


class UIUnavailable(RuntimeError):
    """Raised when the optional UI extra (fastapi + uvicorn) is not installed."""


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


def build_ui_app(results_dir: str | Path = "results/published"):
    """Build the FastAPI app. Routes:
      GET /            -> the dashboard (re-rendered from the latest results)
      GET /healthz     -> liveness
      GET /api/run     -> latest run JSON
      GET /api/crossover -> latest crossover dataset JSON
      GET /api/cost-curve -> {arm: {N: tokens}} derived from the dataset
    """
    _require_ui()
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse

    results_dir = Path(results_dir)
    app = FastAPI(title="Decision Grounding Bench", docs_url="/api/docs")

    @app.get("/", response_class=HTMLResponse)
    def index():  # noqa: ANN202
        run, dataset = load_results(results_dir)
        if run is None:
            return HTMLResponse(_EMPTY.format(dir=results_dir))
        return HTMLResponse(build_dashboard(run, dataset))

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


def run_ui(results_dir: str | Path = "results/published", host: str = "127.0.0.1", port: int = 8099) -> None:
    """Serve the UI with uvicorn (the `decisiongrounding ui` command)."""
    _require_ui()
    import uvicorn

    app = build_ui_app(results_dir)
    print(f"Decision Grounding Bench UI -> http://{host}:{port}  (results: {results_dir})")
    uvicorn.run(app, host=host, port=port, log_level="warning")
