#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Latency and memory harness for the ``rac`` engine across a scale corpus.

Drives ``rac`` strictly as an external CLI / MCP server on ``PATH`` (no engine
imports, DG-ADR-0001) and records everything needed to re-plot a corpus-size
curve later:

    python scale/measure.py --corpus DIR --out RESULTS.json \
        [--queries N] [--runs N] [--timeout S] [--mcp-cache] [--skip OPS]

Measured surfaces:

  a. CLI one-shot wall-clock (median of --runs) and peak RSS for
     ``validate`` / ``find`` / ``resolve`` / ``relationships --validate`` /
     ``export --documents``.
  b. Warm retrieval against ``rac mcp`` over MCP JSON-RPC 2.0 on stdio:
     p50/p95/p99 per tool (search_artifacts / get_artifact / get_related)
     plus the server's peak RSS.
  c. Incremental: append a harmless line to ~1k files, then re-run
     ``validate`` and one warm MCP search, so the cost can be read as
     changeset-bound vs corpus-bound.

Every long-running child starts in its own session (``start_new_session``); a
timeout kills the whole process group so a hung large-corpus run cannot wedge
the box.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _common import (  # noqa: E402
    ADJECTIVES,
    QUERY_TERMS,
    SUBSYSTEMS,
    TOPICS,
    artifact_id,
)

SCHEMA_VERSION = 1
DEFAULT_TIMEOUT = 1800
DEFAULT_RUNS = 3
DEFAULT_QUERIES = 50
INCREMENTAL_FILES = 1000

CLI_OPS = ("validate", "find", "resolve", "relationships", "export")
WARM_TOOLS = ("search_artifacts", "get_artifact", "get_related")
ALL_OPS = CLI_OPS + ("warm", "incremental")

# Warm-query classes (ADR-100 measurement). A single query class made every warm
# measurement a payload-serialisation benchmark, so each tool now runs its
# *natural* classes and the per-class percentiles are reported separately:
#
#   broad     — one common vocabulary term (the historical vocabulary). It matches
#               a fixed fraction (~10%) of the corpus at every size, so the response
#               carries thousands of matches and the latency is dominated by
#               serialising that payload, not by the index. Reported for continuity,
#               but it is mode-independent and payload-bound — not a gate signal.
#   selective — a three-term AND across the topic / subsystem / adjective pools.
#               These rarely co-occur, so the match set is a small handful and the
#               measurement reflects the query path (candidate generation + scoring
#               of a few candidates), not payload serialisation.
#   lookup    — an exact artifact id, the natural argument for get_artifact /
#               get_related (resolution + edge/neighbourhood shaping for one node).
#
# search runs broad+selective; the id tools run lookup. Each tool's top-level
# block stays its historical primary class (search->broad, id tools->lookup) so
# existing fields are unchanged; the ``classes`` sub-object is purely additive.
WARM_CLASSES: dict[str, tuple[str, ...]] = {
    "search_artifacts": ("broad", "selective"),
    "get_artifact": ("lookup",),
    "get_related": ("lookup",),
}


def _selective_query(i: int) -> str:
    """A deterministic multi-term AND query that matches a small handful.

    One topic, one subsystem, one adjective — three independent vocabulary pools
    whose terms co-occur in only a few artifacts, so the AND result set stays
    small at any corpus size (the index prunes to those candidates and scores
    only them). Pure function of ``i`` and the frozen ``_common`` vocabulary, so
    the harness needs no corpus read to reproduce it.
    """
    return (
        f"{TOPICS[i % len(TOPICS)]} "
        f"{SUBSYSTEMS[i % len(SUBSYSTEMS)]} "
        f"{ADJECTIVES[i % len(ADJECTIVES)]}"
    )


def _lookup_id(i: int, corpus_count: int) -> str:
    """The exact id for warm call ``i``, spread across the whole corpus."""
    step = max(1, corpus_count // max(1, DEFAULT_QUERIES))
    idx = (i * step) % max(1, corpus_count) if corpus_count else 0
    return artifact_id(idx)


def _class_arguments(tool: str, cls: str, i: int, corpus_count: int) -> dict:
    """Arguments for warm call ``i`` of ``tool`` under query class ``cls``."""
    if cls == "broad":
        return {"query": QUERY_TERMS[i % len(QUERY_TERMS)]}
    if cls == "selective":
        return {"query": _selective_query(i)}
    if cls == "lookup":
        return {"id": _lookup_id(i, corpus_count)}
    raise ValueError(cls)


def _warm_stats(latencies_ms: list[float]) -> dict:
    """The per-tool / per-class latency summary (shape unchanged from v1)."""
    return {
        "count": len(latencies_ms),
        "p50_ms": round(_percentile(latencies_ms, 50), 4),
        "p95_ms": round(_percentile(latencies_ms, 95), 4),
        "p99_ms": round(_percentile(latencies_ms, 99), 4),
        "min_ms": round(min(latencies_ms), 4),
        "max_ms": round(max(latencies_ms), 4),
    }


# --- process / memory primitives -----------------------------------------


def _read_vmhwm_kb(pid: int) -> int:
    """Peak resident set (VmHWM, kB) for ``pid`` from /proc, or 0 if gone."""
    try:
        with open(f"/proc/{pid}/status", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("VmHWM:"):
                    return int(line.split()[1])
    except (FileNotFoundError, ProcessLookupError, ValueError, PermissionError):
        pass
    return 0


class _RssSampler:
    """Polls a pid's VmHWM on a thread; VmHWM is monotonic so max == peak."""

    def __init__(self, pid: int, interval: float = 0.02) -> None:
        self._pid = pid
        self._interval = interval
        self._stop = threading.Event()
        self.peak_kb = 0
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self) -> None:
        while not self._stop.is_set():
            v = _read_vmhwm_kb(self._pid)
            if v > self.peak_kb:
                self.peak_kb = v
            self._stop.wait(self._interval)

    def __enter__(self) -> "_RssSampler":
        self._thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        # One final read captures the high-water mark just before exit.
        v = _read_vmhwm_kb(self._pid)
        if v > self.peak_kb:
            self.peak_kb = v
        self._stop.set()
        self._thread.join(timeout=1)


def _killpg(pid: int) -> None:
    try:
        os.killpg(os.getpgid(pid), signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def run_timed(argv: list[str], timeout: int, *, discard_stdout: bool = False) -> dict:
    """Run ``argv`` once; return wall time, peak RSS, exit code — or a timeout."""
    stdout = subprocess.DEVNULL if discard_stdout else subprocess.PIPE
    start = time.perf_counter()
    proc = subprocess.Popen(
        argv, stdout=stdout, stderr=subprocess.PIPE, start_new_session=True
    )
    timed_out = False
    with _RssSampler(proc.pid) as sampler:
        try:
            proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            _killpg(proc.pid)
            try:
                proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
    wall = time.perf_counter() - start
    if timed_out:
        return {"timeout": True, "limit_s": timeout}
    return {
        "wall_s": round(wall, 6),
        "peak_rss_kb": sampler.peak_kb,
        "exit_code": proc.returncode,
    }


def _median(values: list[float]) -> float:
    s = sorted(values)
    n = len(s)
    if n == 0:
        return 0.0
    mid = n // 2
    return s[mid] if n % 2 else (s[mid - 1] + s[mid]) / 2


def _percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile in the same units as ``values``."""
    if not values:
        return 0.0
    s = sorted(values)
    rank = max(1, int(round(pct / 100.0 * len(s))))
    return s[min(rank, len(s)) - 1]


# --- CLI one-shot measurements --------------------------------------------


def _cli_argv(op: str, corpus: str, term: str, an_id: str) -> tuple[list[str], bool]:
    """(argv, discard_stdout) for one CLI op."""
    if op == "validate":
        return (["rac", "validate", corpus], False)
    if op == "find":
        return (["rac", "find", term, corpus], False)
    if op == "resolve":
        return (["rac", "resolve", an_id, corpus], False)
    if op == "relationships":
        return (["rac", "relationships", corpus, "--validate"], False)
    if op == "export":
        # Large payload straight to /dev/null: we time the engine, not our pipe.
        return (["rac", "export", "--documents", corpus], True)
    raise ValueError(op)


def measure_cli(corpus: str, runs: int, timeout: int, skip: set[str],
                term: str, an_id: str) -> dict:
    results: dict[str, dict] = {}
    for op in CLI_OPS:
        if op in skip:
            results[op] = {"skipped": True}
            continue
        samples: list[dict] = []
        for _ in range(runs):
            argv, discard = _cli_argv(op, corpus, term, an_id)
            samples.append(run_timed(argv, timeout, discard_stdout=discard))
            if samples[-1].get("timeout"):
                break
        if samples[-1].get("timeout"):
            results[op] = samples[-1]
            continue
        walls = [s["wall_s"] for s in samples]
        results[op] = {
            "runs": len(samples),
            "median_s": round(_median(walls), 6),
            "min_s": round(min(walls), 6),
            "max_s": round(max(walls), 6),
            "peak_rss_kb": max(s["peak_rss_kb"] for s in samples),
            "exit_code": samples[-1]["exit_code"],
        }
    return results


# --- minimal MCP JSON-RPC 2.0 stdio client --------------------------------


class McpClient:
    """A minimal stdlib MCP client over a ``rac mcp`` stdio subprocess.

    Speaks exactly what the harness needs: the ``initialize`` handshake, the
    ``notifications/initialized`` notice, then ordered ``tools/call`` requests.
    Responses arrive in request order over a single stdio pipe, so a blocking
    readline per call is sufficient and keeps the client dependency-free.
    """

    def __init__(self, corpus: str, cache: bool, index: bool = False) -> None:
        argv = ["rac", "mcp", "--root", corpus]
        if index:
            # ADR-100/101 persistent-index serving mode; mutually exclusive with
            # --cache upstream (the engine prefers --index when both are given).
            argv.append("--index")
        elif cache:
            argv.append("--cache")
        self._proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            start_new_session=True,
        )
        self._id = 0

    @property
    def pid(self) -> int:
        return self._proc.pid

    def _send(self, obj: dict) -> None:
        assert self._proc.stdin is not None
        self._proc.stdin.write(json.dumps(obj) + "\n")
        self._proc.stdin.flush()

    def _read(self) -> dict:
        assert self._proc.stdout is not None
        line = self._proc.stdout.readline()
        if not line:
            err = ""
            if self._proc.stderr is not None:
                err = self._proc.stderr.read()
            raise RuntimeError(f"rac mcp closed its stream unexpectedly: {err[:400]}")
        return json.loads(line)

    def _request(self, method: str, params: dict) -> dict:
        self._id += 1
        self._send({"jsonrpc": "2.0", "id": self._id, "method": method,
                    "params": params})
        return self._read()

    def initialize(self) -> None:
        self._request("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "scale-measure", "version": "0.1.0"},
        })
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def call(self, tool: str, arguments: dict) -> dict:
        resp = self._request("tools/call", {"name": tool, "arguments": arguments})
        if "error" in resp:
            raise RuntimeError(f"{tool} error: {resp['error']}")
        return resp

    def close(self) -> None:
        try:
            if self._proc.stdin:
                self._proc.stdin.close()
        except OSError:
            pass
        _killpg(self._proc.pid)
        try:
            self._proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self._proc.kill()


def _tool_arguments(tool: str, i: int, corpus_count: int) -> dict:
    """Distinct, deterministic arguments for warm call ``i``."""
    if tool == "search_artifacts":
        return {"query": QUERY_TERMS[i % len(QUERY_TERMS)]}
    # Spread ids across the whole corpus so caches are exercised, not just the
    # first shard. All ids in [0, corpus_count) exist by construction.
    step = max(1, corpus_count // max(1, DEFAULT_QUERIES))
    idx = (i * step) % max(1, corpus_count) if corpus_count else 0
    return {"id": artifact_id(idx)}


def measure_warm(corpus: str, corpus_count: int, queries: int,
                 cache: bool, index: bool = False) -> dict:
    client = McpClient(corpus, cache, index)
    per_tool: dict[str, dict] = {}
    with _RssSampler(client.pid) as sampler:
        try:
            client.initialize()
            for tool in WARM_TOOLS:
                classes = WARM_CLASSES[tool]
                per_class: dict[str, dict] = {}
                for cls in classes:
                    # Warm-up call (untimed): pays any first-touch build cost.
                    client.call(tool, _class_arguments(tool, cls, 0, corpus_count))
                    latencies_ms: list[float] = []
                    for i in range(queries):
                        args = _class_arguments(tool, cls, i, corpus_count)
                        t0 = time.perf_counter()
                        client.call(tool, args)
                        latencies_ms.append((time.perf_counter() - t0) * 1000.0)
                    per_class[cls] = _warm_stats(latencies_ms)
                # Top-level block = the tool's historical primary class (search ->
                # broad, id tools -> lookup), so existing fields are byte-unchanged;
                # every class (including selective) is reported under ``classes``.
                per_tool[tool] = {**per_class[classes[0]], "classes": per_class}
        finally:
            client.close()
    return {
        "cache": cache,
        "queries": queries,
        "tools": per_tool,
        "server_peak_rss_kb": sampler.peak_kb,
    }


# --- incremental measurement ----------------------------------------------


def _touch_files(corpus: Path, limit: int) -> int:
    """Append one harmless HTML comment line to up to ``limit`` .md files."""
    files = sorted(p for p in corpus.rglob("*.md"))
    touched = 0
    for path in files[:limit]:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(f"\n<!-- incremental: touched rev {touched} -->\n")
        touched += 1
    return touched


def measure_incremental(corpus: str, corpus_count: int, timeout: int,
                        cache: bool, index: bool = False) -> dict:
    touched = _touch_files(Path(corpus), INCREMENTAL_FILES)
    validate = run_timed(["rac", "validate", corpus], timeout)

    client = McpClient(corpus, cache, index)
    warm: dict = {}
    with _RssSampler(client.pid) as sampler:
        try:
            client.initialize()
            client.call("search_artifacts",
                        _tool_arguments("search_artifacts", 0, corpus_count))
            t0 = time.perf_counter()
            client.call("search_artifacts",
                        _tool_arguments("search_artifacts", 1, corpus_count))
            warm = {"search_ms": round((time.perf_counter() - t0) * 1000.0, 4)}
        finally:
            client.close()
    warm["server_peak_rss_kb"] = sampler.peak_kb

    return {
        "files_modified": touched,
        "validate": validate,
        "warm_search": warm,
    }


# --- environment provenance -----------------------------------------------


def _node_string() -> str:
    model = "unknown-cpu"
    cores = 0
    try:
        with open("/proc/cpuinfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("model name"):
                    model = line.split(":", 1)[1].strip()
                    cores += 1
    except OSError:
        pass
    mem = "unknown-mem"
    try:
        with open("/proc/meminfo", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    kb = int(line.split()[1])
                    mem = f"{kb / (1024 * 1024):.1f} GiB"
                    break
    except OSError:
        pass
    return f"{model} x{cores or '?'}, {mem}"


def _engine_version() -> str:
    try:
        out = subprocess.run(["rac", "--version"], capture_output=True, text=True,
                             check=False)
        return (out.stdout or out.stderr).strip()
    except OSError:
        return "unavailable"


def _manifest_sha(corpus: Path) -> str | None:
    manifest = corpus / "manifest.json"
    if not manifest.is_file():
        return None
    try:
        return json.loads(manifest.read_text(encoding="utf-8")).get("content_sha256")
    except (OSError, json.JSONDecodeError):
        return None


def _corpus_count(corpus: Path) -> int:
    manifest = corpus / "manifest.json"
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(data.get("count"), int):
                return data["count"]
        except (OSError, json.JSONDecodeError):
            pass
    return sum(1 for _ in corpus.rglob("*.md"))


# --- driver ----------------------------------------------------------------


def _serve_mode(cache: bool, index: bool) -> str:
    """The recorded serving mode: index wins over cache wins over the fresh path."""
    if index:
        return "index"
    if cache:
        return "cache"
    return "no-cache"


def measure(corpus: Path, queries: int, runs: int, timeout: int,
            cache: bool, skip: set[str], index: bool = False) -> dict:
    count = _corpus_count(corpus)
    corpus_str = str(corpus)
    # A term and id known to be present, for find/resolve one-shots.
    term = QUERY_TERMS[0]
    an_id = artifact_id(0)

    measurements: dict = {}
    measurements["cli_oneshot"] = measure_cli(
        corpus_str, runs, timeout, skip, term, an_id
    )
    if "warm" in skip:
        measurements["warm_retrieval"] = {"skipped": True}
    else:
        measurements["warm_retrieval"] = measure_warm(
            corpus_str, count, queries, cache, index
        )
    if "incremental" in skip:
        measurements["incremental"] = {"skipped": True}
    else:
        measurements["incremental"] = measure_incremental(
            corpus_str, count, timeout, cache, index
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "corpus": {
            "count": count,
            "path": corpus_str,
            "manifest_sha": _manifest_sha(corpus),
        },
        "node": _node_string(),
        "engine": {"version": _engine_version()},
        "mode": _serve_mode(cache, index),
        "measurements": measurements,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, required=True,
                        help="Generated scale corpus directory.")
    parser.add_argument("--out", type=Path, required=True,
                        help="Results JSON path.")
    parser.add_argument("--queries", type=int, default=DEFAULT_QUERIES,
                        help=f"Warm calls per tool (default: {DEFAULT_QUERIES}).")
    parser.add_argument("--runs", type=int, default=DEFAULT_RUNS,
                        help=f"CLI one-shot repetitions (default: {DEFAULT_RUNS}).")
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT,
                        help=f"Per-command timeout seconds (default: {DEFAULT_TIMEOUT}).")
    parser.add_argument("--mcp-cache", action="store_true",
                        help="Serve MCP with --cache (records mode='cache').")
    parser.add_argument("--mcp-index", action="store_true",
                        help="Serve MCP with --index, the persistent corpus "
                             "index (records mode='index', ADR-100/101).")
    parser.add_argument("--skip", default="",
                        help="Comma-separated ops to skip: "
                             + ", ".join(ALL_OPS) + ".")
    args = parser.parse_args(argv)

    if not args.corpus.is_dir():
        parser.error(f"corpus not found: {args.corpus}")
    if args.mcp_cache and args.mcp_index:
        parser.error("--mcp-cache and --mcp-index are mutually exclusive")
    skip = {s.strip() for s in args.skip.split(",") if s.strip()}
    unknown = skip - set(ALL_OPS)
    if unknown:
        parser.error(f"unknown --skip ops: {sorted(unknown)}")

    results = measure(args.corpus, args.queries, args.runs, args.timeout,
                      args.mcp_cache, skip, args.mcp_index)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(results, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")

    warm = results["measurements"].get("warm_retrieval", {})
    search = warm.get("tools", {}).get("search_artifacts", {})
    print(f"measured {results['corpus']['count']} artifacts "
          f"(mode={results['mode']}) -> {args.out}")
    if search:
        print(f"  search_artifacts warm (broad) p50={search['p50_ms']}ms "
              f"p99={search['p99_ms']}ms")
        selective = search.get("classes", {}).get("selective")
        if selective:
            print(f"  search_artifacts warm (selective) p50={selective['p50_ms']}ms "
                  f"p99={selective['p99_ms']}ms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
