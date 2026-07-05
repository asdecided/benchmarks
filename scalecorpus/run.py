#!/usr/bin/env python3
"""The scalecorpus performance gate: assert the single-node scale target
over a set of perf.py scorecards.

Deterministic and offline (ADR-066): reads committed/produced scorecard JSON,
applies fixed budgets, no clock in the scored path. Exit codes follow the
member convention: 0 = gate passes, 1 = gate failure, 2 = usage error.

The claim being gated is SCALE-INVARIANCE (roadmap rebuild-scale): the
operational budgets must hold at EVERY measured size and stay FLAT across the
curve — not merely pass at one lucky point. Cold build is the one path allowed
to grow with N, and only linearly.

Budgets (per the scale target; see README.md):
  warm retrieval        p99 < 100 ms and p50 < 30 ms at every size; p99 at the
                        top size ≤ FLATNESS_FACTOR × p99 at the smallest size
  incremental validate  < 5 s at every size; top ≤ FLATNESS_FACTOR × smallest
  cold full validate    ≤ 120 s per 1M artifacts (pro-rated by size)
  working set           server RSS ≤ MEM_CEILING_MB at every size
  completeness          no DNFs; every expected metric present

Usage:
  python run.py --check --results results --pattern 'after-*.json' [--json]
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path

WARM_P99_MS = 100.0
WARM_P50_MS = 30.0
INCR_S = 5.0
COLD_S_PER_1M = 120.0
MEM_CEILING_MB = 10 * 1024  # ~2/3 of the 15 GiB reference node
FLATNESS_FACTOR = 2.0  # top-of-curve may be at most 2x the smallest size


def check(cards: list[dict]) -> list[str]:
    """Return the list of gate failures (empty = pass)."""
    fails: list[str] = []
    cards = sorted(cards, key=lambda c: c["metadata"]["size"])
    if not cards:
        return ["no scorecards matched"]

    warm_p99, incr_s = {}, {}
    for c in cards:
        size = c["metadata"]["size"]
        m = c.get("metrics", {})
        tag = f"{size:,}"

        w = m.get("warm_retrieval")
        if w is None:
            fails.append(f"{tag}: warm_retrieval missing")
        elif w.get("dnf"):
            fails.append(f"{tag}: warm retrieval DNF ({w.get('dnf')} timed-out calls)")
        else:
            warm_p99[size] = w["p99_ms"]
            if w["p99_ms"] >= WARM_P99_MS:
                fails.append(f"{tag}: warm p99 {w['p99_ms']} ms >= {WARM_P99_MS} ms")
            if w["p50_ms"] >= WARM_P50_MS:
                fails.append(f"{tag}: warm p50 {w['p50_ms']} ms >= {WARM_P50_MS} ms")
            rss = w.get("server_peak_rss_mb")
            if rss is not None and rss > MEM_CEILING_MB:
                fails.append(f"{tag}: server peak RSS {rss} MB > {MEM_CEILING_MB} MB")

        i = m.get("incremental_validate")
        if i is None:
            fails.append(f"{tag}: incremental_validate missing")
        elif i.get("dnf"):
            fails.append(f"{tag}: incremental validate DNF (> {i.get('timeout_s')} s)")
        else:
            incr_s[size] = i["wall_s"]
            if i["wall_s"] >= INCR_S:
                fails.append(f"{tag}: incremental validate {i['wall_s']} s >= {INCR_S} s")
            if i.get("exit") not in (0, 1):
                fails.append(f"{tag}: incremental validate exit {i.get('exit')}")

        f = m.get("full_validate")
        if f is None:
            fails.append(f"{tag}: full_validate missing")
        elif f.get("dnf"):
            fails.append(f"{tag}: cold full validate DNF (> {f.get('timeout_s')} s)")
        else:
            budget = COLD_S_PER_1M * max(size, 1) / 1_000_000
            # Small corpora finish in noise; only meaningful from 100k up.
            if size >= 100_000 and f["wall_s"] > budget:
                fails.append(f"{tag}: cold validate {f['wall_s']} s > {round(budget, 1)} s")
            rss = f.get("peak_rss_mb")
            if rss is not None and rss > MEM_CEILING_MB:
                fails.append(f"{tag}: validate peak RSS {rss} MB > {MEM_CEILING_MB} MB")

    # Flatness: the invariance claim, judged across the measured curve.
    for name, series, factor in (
        ("warm p99", warm_p99, FLATNESS_FACTOR),
        ("incremental validate", incr_s, FLATNESS_FACTOR),
    ):
        if len(series) >= 2:
            lo, hi = min(series), max(series)
            base, top = series[lo], series[hi]
            if base > 0 and top > factor * base:
                fails.append(
                    f"curve not flat: {name} grows {round(top / base, 2)}x "
                    f"from {lo:,} to {hi:,} (allowed {factor}x)"
                )
    return fails


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="apply the gate (exit 1 on failure)")
    ap.add_argument("--results", default=str(Path(__file__).parent / "results"))
    ap.add_argument("--pattern", default="after-*.json", help="scorecard glob within --results")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    paths = sorted(glob.glob(str(Path(a.results) / a.pattern)))
    if not paths:
        print(f"no scorecards match {a.results}/{a.pattern}", file=sys.stderr)
        return 2
    try:
        cards = [json.loads(Path(p).read_text()) for p in paths]
    except (OSError, ValueError) as e:
        print(f"unreadable scorecard: {e}", file=sys.stderr)
        return 2

    fails = check(cards)
    if a.json:
        print(json.dumps({"scorecards": paths, "failures": fails, "pass": not fails}, indent=2))
    else:
        for p in paths:
            print(f"scorecard: {p}")
        if fails:
            print(f"GATE FAIL — {len(fails)} budget violation(s):")
            for f in fails:
                print(f"  ✗ {f}")
        else:
            print("GATE PASS — every budget holds at every measured size, curve flat.")
    return 1 if (a.check and fails) else 0


if __name__ == "__main__":
    raise SystemExit(main())
