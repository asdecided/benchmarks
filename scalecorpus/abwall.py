#!/usr/bin/env python3
"""Interleaved A/B wall-clock comparison of two rac engines.

Runs the same command list against two engine installations (two venv ``rac``
executables), INTERLEAVED (A,B,A,B,...) so slow drift on the host biases
neither side, each run in a fresh process, with one unmeasured warm-up pair
per command. Reports per-command medians and the B/A ratio. Exit codes must
match between sides for the comparison to count — a mismatch is reported and
the command excluded from ratios (identical answers are the precondition for
"less work, same answer").

Usage:
  python abwall.py --a /path/legacy-venv/bin/rac --b /path/rebuilt-venv/bin/rac \
      --corpus /path/c10k --reps 5 --out results/abwall-10k.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generate


def commands(corpus: str, size: int) -> list[list[str]]:
    return [
        ["validate", corpus],
        ["index", corpus, "--json"],
        ["find", generate.MID[0], corpus, "--json"],
        ["resolve", generate.artifact_id(size // 2), corpus, "--json"],
        ["relationships", corpus, "--validate"],
        ["export", corpus, "--documents"],
    ]


def _run(binary: str, argv: list[str], timeout: float) -> tuple[float, int]:
    t0 = time.monotonic()
    proc = subprocess.run([binary, *argv], capture_output=True, timeout=timeout)
    return time.monotonic() - t0, proc.returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--a", required=True, help="engine A rac executable (baseline)")
    ap.add_argument("--b", required=True, help="engine B rac executable (candidate)")
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--size", type=int, required=True)
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--timeout", type=float, default=600.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    report = []
    for argv in commands(a.corpus, a.size):
        _run(a.a, argv, a.timeout)  # warm-up pair, unmeasured
        _run(a.b, argv, a.timeout)
        times_a, times_b, exits_a, exits_b = [], [], set(), set()
        for _ in range(a.reps):
            ta, ea = _run(a.a, argv, a.timeout)
            tb, eb = _run(a.b, argv, a.timeout)
            times_a.append(ta)
            times_b.append(tb)
            exits_a.add(ea)
            exits_b.add(eb)
        med_a, med_b = statistics.median(times_a), statistics.median(times_b)
        entry = {
            "argv": argv,
            "median_a_s": round(med_a, 3),
            "median_b_s": round(med_b, 3),
            "exits_a": sorted(exits_a),
            "exits_b": sorted(exits_b),
            "exit_match": exits_a == exits_b,
            "ratio_b_over_a": round(med_b / med_a, 3) if exits_a == exits_b and med_a > 0 else None,
        }
        report.append(entry)
        print(f"{' '.join(argv[:2]):40s} A {med_a:7.2f}s  B {med_b:7.2f}s  "
              f"ratio {entry['ratio_b_over_a']}", flush=True)

    payload = {
        "metadata": {"a": a.a, "b": a.b, "corpus": a.corpus, "size": a.size, "reps": a.reps},
        "commands": report,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(payload, indent=2) + "\n")
    print(f"scorecard -> {a.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
