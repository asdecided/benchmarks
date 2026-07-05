#!/usr/bin/env python3
"""Per-tool warm MCP latency probe (supplement to perf.py for tools its mixed
workload omits: get_summary and find_decisions path-mode).

Usage: python toolbench.py --rac /path/to/venv/bin/rac --corpus DIR --calls 10 [--cache]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time


async def run(rac: str, corpus: str, calls: int, cache: bool) -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    args = ["mcp", "--root", corpus] + (["--cache"] if cache else [])
    out: dict[str, dict] = {}
    errlog = open(os.devnull, "w")
    async with stdio_client(StdioServerParameters(command=rac, args=args), errlog=errlog) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            for tool, targs in (
                ("get_summary", {}),
                ("find_decisions", {"path": "shard-00000"}),
            ):
                await s.call_tool(tool, targs)  # warm-up, excluded
                samples = []
                for _ in range(calls):
                    t0 = time.monotonic()
                    await s.call_tool(tool, targs)
                    samples.append((time.monotonic() - t0) * 1000)
                out[tool] = {
                    "p50_ms": round(statistics.median(samples), 1),
                    "max_ms": round(max(samples), 1),
                    "n": calls,
                }
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rac", required=True)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--calls", type=int, default=10)
    ap.add_argument("--cache", action="store_true")
    a = ap.parse_args()
    print(json.dumps(asyncio.run(run(a.rac, a.corpus, a.calls, a.cache))))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
