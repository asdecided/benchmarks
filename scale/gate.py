#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""The rerunnable scale performance gate.

Asserts the SCALE_TARGET budgets against one or more ``measure.py`` results
files and prints a plain report. With a single file it checks absolute
budgets; with several (one per corpus size) it also checks *flatness* — warm
latency and incremental cost at the largest size must stay within 1.5x of the
smallest, which is the property that separates changeset-bound cost from
corpus-bound cost.

    python scale/gate.py RESULTS.json [RESULTS.json ...]

Exit 0 when every budget holds, 1 otherwise. This is an evidence gate for a
scale run, never a merge gate on the corpus.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# The single-node scale budgets. Documented in scale/README.md; the gate is the
# executable copy.
SCALE_TARGET = {
    "warm_p50_ms": 30.0,          # warm retrieval median, per tool
    "warm_p99_ms": 100.0,         # warm retrieval tail, per tool
    "incremental_validate_s": 5.0,  # re-validate after a ~1k-file changeset
    "cold_build_s_per_1m": 120.0,  # cold `rac validate`, normalised to 1M files
    "working_set_kb": 10 * 1024 * 1024,  # ~10 GB peak RSS ceiling
    "flatness_ratio": 1.5,        # largest-size / smallest-size tolerance
}

WARM_TOOLS = ("search_artifacts", "get_artifact", "get_related")


class Report:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.failures = 0

    def check(self, label: str, ok: bool | None, detail: str) -> None:
        if ok is None:
            mark = "SKIP"
        elif ok:
            mark = "PASS"
        else:
            mark = "FAIL"
            self.failures += 1
        self.lines.append(f"  {mark}  {label}: {detail}")

    def section(self, title: str) -> None:
        self.lines.append(title)


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _warm_tools(result: dict) -> dict:
    return result.get("measurements", {}).get("warm_retrieval", {}).get("tools", {})


def _gate_one(result: dict, path: Path, report: Report) -> None:
    count = result.get("corpus", {}).get("count", 0)
    report.section(f"[{path.name}] count={count} mode={result.get('mode')}")
    m = result.get("measurements", {})

    # Warm retrieval budgets, per tool.
    warm = m.get("warm_retrieval", {})
    if warm.get("skipped"):
        report.check("warm_retrieval", None, "skipped")
    else:
        tools = warm.get("tools", {})
        for tool in WARM_TOOLS:
            t = tools.get(tool)
            if not t:
                report.check(f"warm.{tool}", False, "missing from results")
                continue
            # Gate on the representative query class when present: 'selective'
            # for search (the broad class returns ~10% of the corpus and
            # measures payload serialization, which is mode-independent and
            # reported but not gated), 'lookup' for the id-shaped tools. The
            # top-level p50_ms/p99_ms fields keep their historical meaning and
            # remain in the results JSON; older results without classes gate
            # on them unchanged. Budgets are untouched.
            classes = t.get("classes", {})
            gated = classes.get("selective") or classes.get("lookup") or t
            p50, p99 = gated["p50_ms"], gated["p99_ms"]
            report.check(
                f"warm.{tool}.p50", p50 < SCALE_TARGET["warm_p50_ms"],
                f"{p50:.2f}ms (budget <{SCALE_TARGET['warm_p50_ms']:.0f}ms)")
            report.check(
                f"warm.{tool}.p99", p99 < SCALE_TARGET["warm_p99_ms"],
                f"{p99:.2f}ms (budget <{SCALE_TARGET['warm_p99_ms']:.0f}ms)")
        rss = warm.get("server_peak_rss_kb", 0)
        report.check("warm.server_rss", rss <= SCALE_TARGET["working_set_kb"],
                     f"{rss / 1024 / 1024:.2f}GB "
                     f"(budget <={SCALE_TARGET['working_set_kb'] / 1024 / 1024:.0f}GB)")

    # Incremental re-validate budget.
    inc = m.get("incremental", {})
    if inc.get("skipped"):
        report.check("incremental.validate", None, "skipped")
    else:
        v = inc.get("validate", {})
        if v.get("timeout"):
            report.check("incremental.validate", False,
                         f"timeout at {v.get('limit_s')}s")
        else:
            secs = v.get("wall_s", 0.0)
            report.check(
                "incremental.validate",
                secs < SCALE_TARGET["incremental_validate_s"],
                f"{secs:.2f}s (budget <{SCALE_TARGET['incremental_validate_s']:.0f}s)")

    # Cold build budget, normalised to 1M files.
    cli = m.get("cli_oneshot", {})
    validate = cli.get("validate", {})
    if validate.get("skipped"):
        report.check("cold_build", None, "skipped")
    elif validate.get("timeout"):
        report.check("cold_build", False, f"timeout at {validate.get('limit_s')}s")
    elif count:
        per_1m = validate.get("median_s", 0.0) / count * 1_000_000
        report.check(
            "cold_build.per_1m", per_1m < SCALE_TARGET["cold_build_s_per_1m"],
            f"{per_1m:.1f}s/1M (budget <{SCALE_TARGET['cold_build_s_per_1m']:.0f}s/1M)")


def _flatness(results: list[tuple[Path, dict]], report: Report) -> None:
    """Largest-vs-smallest ratios across the corpus-size curve."""
    ordered = sorted(results, key=lambda pr: pr[1].get("corpus", {}).get("count", 0))
    (small_p, small), (large_p, large) = ordered[0], ordered[-1]
    ratio = SCALE_TARGET["flatness_ratio"]
    report.section(
        f"[flatness] {small.get('corpus', {}).get('count')} -> "
        f"{large.get('corpus', {}).get('count')} (tolerance {ratio}x)")

    def _ratio_check(label: str, base: float | None, big: float | None) -> None:
        if not base or big is None:
            report.check(label, None, "unavailable at one size")
            return
        r = big / base
        report.check(label, r <= ratio, f"{r:.2f}x (small={base:.2f}, large={big:.2f})")

    st, lt = _warm_tools(small), _warm_tools(large)
    for tool in WARM_TOOLS:
        s, l = st.get(tool), lt.get(tool)
        _ratio_check(f"warm.{tool}.p50", s and s.get("p50_ms"), l and l.get("p50_ms"))
        _ratio_check(f"warm.{tool}.p99", s and s.get("p99_ms"), l and l.get("p99_ms"))

    sv = small.get("measurements", {}).get("incremental", {}).get("validate", {})
    lv = large.get("measurements", {}).get("incremental", {}).get("validate", {})
    _ratio_check("incremental.validate", sv.get("wall_s"), lv.get("wall_s"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path, nargs="+",
                        help="One or more measure.py results JSON files.")
    args = parser.parse_args(argv)

    loaded = [(p, _load(p)) for p in args.results]
    report = Report()
    print("SCALE_TARGET gate")
    for path, result in loaded:
        _gate_one(result, path, report)
    if len(loaded) > 1:
        _flatness(loaded, report)

    print("\n".join(report.lines))
    if report.failures:
        print(f"\nGATE FAIL — {report.failures} budget(s) exceeded")
        return 1
    print("\nGATE PASS — all budgets within target")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
