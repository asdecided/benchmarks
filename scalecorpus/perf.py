#!/usr/bin/env python3
"""Scale-corpus performance harness for the RAC engine.

Measures the operational latency budgets from the single-node scale target
against a generated corpus (see ``generate.py``), driving ``rac`` strictly as
an external process on ``PATH`` (DG-ADR-0001 — zero engine imports):

- **warm retrieval** — a long-lived ``rac mcp`` (stdio) session answering
  ``search_artifacts`` / ``get_artifact`` / ``get_related`` calls; per-call
  wall latency, p50/p95/p99, after warm-up. ``--cache`` toggles ADR-099.
- **cold CLI retrieval** — one-shot ``rac find`` / ``rac resolve`` invocations
  (includes interpreter start-up; the CLI contract path).
- **cold full validate** — ``rac validate <corpus>`` from nothing: wall time
  and peak RSS.
- **incremental validate** — re-validate after a ~1,000-artifact changeset
  (the changeset is applied deterministically, then restored).

Every number is emitted in a JSON scorecard with the corpus size, engine
version, and node description, so before/after runs are comparable. A call
that exceeds ``--timeout`` is recorded as DNF, never silently dropped —
failing to finish at scale is a result, not an error.

Usage:
  python perf.py --corpus /path/to/corpus --size 100000 --out results/before-100k.json \
      [--cache] [--calls 200] [--reps 5] [--timeout 600] [--skip warm,cold,full,incr]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate  # deterministic twin of the corpus: ids, terms, changesets

CHANGESET_SIZE = 1000


def _percentiles(samples: list[float]) -> dict[str, float]:
    if not samples:
        return {}
    s = sorted(samples)
    return {
        "n": len(s),
        "p50_ms": round(s[len(s) // 2] * 1000, 2),
        "p95_ms": round(s[min(len(s) - 1, int(len(s) * 0.95))] * 1000, 2),
        "p99_ms": round(s[min(len(s) - 1, int(len(s) * 0.99))] * 1000, 2),
        "mean_ms": round(statistics.fmean(s) * 1000, 2),
        "max_ms": round(s[-1] * 1000, 2),
    }


def query_set(size: int, calls: int) -> list[tuple[str, dict]]:
    """Deterministic mixed workload: point lookups, selective and broad search,
    and graph neighbourhood reads, spread across the corpus."""
    queries: list[tuple[str, dict]] = []
    for k in range(calls):
        idx = (k * 2654435761) % size  # golden-ratio stride: spread, deterministic
        kind = k % 4
        if kind == 0:
            queries.append(("get_artifact", {"id": generate.artifact_id(idx)}))
        elif kind == 1:
            queries.append(("get_related", {"id": generate.artifact_id(idx)}))
        elif kind == 2:
            term = generate.MID[k % len(generate.MID)]
            queries.append(("search_artifacts", {"query": term}))
        else:
            term = generate.RARE[k % len(generate.RARE)]
            queries.append(("search_artifacts", {"query": term}))
    return queries


def _rss_of(pattern: str) -> dict[str, int]:
    """Current and peak RSS (kB) of the first process matching pattern."""
    try:
        pids = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout.split()
        for pid in pids:
            if pid == str(os.getpid()):
                continue
            status = Path(f"/proc/{pid}/status").read_text()
            rss = int(re.search(r"VmRSS:\s+(\d+)", status).group(1))
            hwm = int(re.search(r"VmHWM:\s+(\d+)", status).group(1))
            return {"rss_kb": rss, "peak_kb": hwm}
    except Exception:
        pass
    return {}


async def bench_warm(corpus: str, size: int, calls: int, cache: bool, timeout: float) -> dict:
    """Warm retrieval over a long-lived MCP stdio session."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    args = ["mcp", "--root", corpus] + (["--cache"] if cache else [])
    params = StdioServerParameters(command="rac", args=args)
    samples: list[float] = []
    dnf = 0
    per_tool: dict[str, list[float]] = {}
    rss: dict[str, int] = {}
    queries = query_set(size, calls)
    warmups = min(5, max(1, calls // 20))
    errlog = open(os.devnull, "w")
    async with stdio_client(params, errlog=errlog) as (read, write):
        async with ClientSession(read, write) as session:
            await asyncio.wait_for(session.initialize(), timeout=timeout)
            for tool, arg in queries[:warmups]:  # warm-up, excluded
                try:
                    await asyncio.wait_for(session.call_tool(tool, arg), timeout=timeout)
                except asyncio.TimeoutError:
                    return {"dnf": True, "note": f"warm-up call exceeded {timeout}s", "cache": cache}
            for tool, arg in queries:
                t0 = time.monotonic()
                try:
                    await asyncio.wait_for(session.call_tool(tool, arg), timeout=timeout)
                except asyncio.TimeoutError:
                    dnf += 1
                    continue
                dt = time.monotonic() - t0
                samples.append(dt)
                per_tool.setdefault(tool, []).append(dt)
            rss = _rss_of(f"rac mcp --root {corpus}")
    out = {"cache": cache, "calls": len(samples), "dnf": dnf, **_percentiles(samples)}
    out["per_tool"] = {t: _percentiles(s) for t, s in sorted(per_tool.items())}
    if rss:
        out["server_rss_mb"] = round(rss["rss_kb"] / 1024, 1)
        out["server_peak_rss_mb"] = round(rss["peak_kb"] / 1024, 1)
    return out


# Wrapper that runs a command as its only child and reports the child's wall
# time, exit code, and peak RSS via getrusage — /usr/bin/time is absent here.
_RUSAGE_WRAPPER = (
    "import resource,subprocess,sys,time,json;"
    "t0=time.monotonic();p=subprocess.run(sys.argv[1:],capture_output=True);"
    "w=time.monotonic()-t0;r=resource.getrusage(resource.RUSAGE_CHILDREN);"
    "print(json.dumps({'wall_s':round(w,2),'exit':p.returncode,"
    "'peak_rss_mb':round(r.ru_maxrss/1024,1)}))"
)


def _timed_run(cmd: list[str], timeout: float) -> dict:
    """Run once in a fresh process: wall seconds, exit code, peak RSS."""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", _RUSAGE_WRAPPER, *cmd],
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"dnf": True, "timeout_s": timeout}
    try:
        return json.loads(proc.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"error": proc.stderr[-500:]}


def bench_cold_cli(corpus: str, size: int, reps: int, timeout: float) -> dict:
    """One-shot CLI invocations: rac resolve (point) and rac find (search)."""
    out: dict[str, list[dict]] = {"resolve": [], "find_rare": []}
    for k in range(reps):
        idx = (k * 2654435761) % size
        out["resolve"].append(_timed_run(["rac", "resolve", generate.artifact_id(idx), corpus, "--json"], timeout))
        term = generate.RARE[k % len(generate.RARE)]
        out["find_rare"].append(_timed_run(["rac", "find", term, corpus, "--json"], timeout))
    summary = {}
    for name, runs in out.items():
        walls = [r["wall_s"] for r in runs if "wall_s" in r]
        summary[name] = {
            "runs": runs,
            "median_wall_s": round(statistics.median(walls), 2) if walls else None,
            "dnf": sum(1 for r in runs if r.get("dnf")),
        }
    return summary


def bench_full_validate(corpus: str, timeout: float) -> dict:
    return _timed_run(["rac", "validate", corpus], timeout)


def apply_changeset(corpus: str, size: int) -> list[Path]:
    """Deterministically rewrite ~CHANGESET_SIZE artifacts (alternate seed)."""
    changed: list[Path] = []
    root = Path(corpus)
    n = min(CHANGESET_SIZE, size)
    for k in range(n):
        idx = (k * 2654435761) % size
        rel, content = generate.render(idx, seed=99)
        p = root / rel
        p.write_bytes(content.encode())
        changed.append(p)
    return changed


def restore_changeset(corpus: str, size: int, seed: int) -> None:
    root = Path(corpus)
    n = min(CHANGESET_SIZE, size)
    for k in range(n):
        idx = (k * 2654435761) % size
        rel, content = generate.render(idx, seed=seed)
        (root / rel).write_bytes(content.encode())


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--size", type=int, required=True, help="artifact count in the corpus")
    ap.add_argument("--seed", type=int, default=7, help="seed the corpus was generated with")
    ap.add_argument("--out", required=True, help="scorecard JSON path")
    ap.add_argument("--cache", action="store_true", help="serve warm calls with ADR-099 --cache")
    ap.add_argument("--calls", type=int, default=200, help="warm MCP calls to measure")
    ap.add_argument("--reps", type=int, default=5, help="cold CLI repetitions")
    ap.add_argument("--timeout", type=float, default=600.0, help="per-call / per-run cap (s)")
    ap.add_argument("--skip", default="", help="comma list of: warm,cold,full,incr")
    ap.add_argument("--label", default="", help="free-form label (e.g. engine build)")
    a = ap.parse_args()
    skip = set(filter(None, a.skip.split(",")))

    rac_version = subprocess.run(["rac", "--version"], capture_output=True, text=True).stdout.strip()
    scorecard: dict = {
        "metadata": {
            "corpus": a.corpus,
            "size": a.size,
            "seed": a.seed,
            "rac_version": rac_version,
            "label": a.label,
            "cpu_count": os.cpu_count(),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        },
        "metrics": {},
    }

    if "warm" not in skip:
        print(f"[warm] mcp stdio, cache={a.cache}, {a.calls} calls ...", flush=True)
        try:
            scorecard["metrics"]["warm_retrieval"] = asyncio.run(
                bench_warm(a.corpus, a.size, a.calls, a.cache, a.timeout)
            )
        except Exception as e:  # a dead server (e.g. OOM-killed) is a result
            scorecard["metrics"]["warm_retrieval"] = {
                "cache": a.cache, "crashed": True, "error": f"{type(e).__name__}: {e}"[:500],
            }
    if "cold" not in skip:
        print(f"[cold] cli one-shots, {a.reps} reps ...", flush=True)
        scorecard["metrics"]["cold_cli"] = bench_cold_cli(a.corpus, a.size, a.reps, a.timeout)
    if "full" not in skip:
        print("[full] rac validate (cold, whole corpus) ...", flush=True)
        scorecard["metrics"]["full_validate"] = bench_full_validate(a.corpus, a.timeout)
    if "incr" not in skip:
        print(f"[incr] validate after a {min(CHANGESET_SIZE, a.size)}-artifact changeset ...", flush=True)
        apply_changeset(a.corpus, a.size)
        try:
            scorecard["metrics"]["incremental_validate"] = bench_full_validate(a.corpus, a.timeout)
        finally:
            restore_changeset(a.corpus, a.size, a.seed)

    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(scorecard, indent=2) + "\n")
    print(json.dumps(scorecard["metrics"], indent=2))
    print(f"scorecard -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
