#!/usr/bin/env python3
"""Deterministic work counts: how many times the engine's hot seams run for
one command, counted by code-object identity via sys.setprofile.

This is the profile-based evidence that the engine does less work for the
same answer: identical exit codes and output, lower call counts. It runs the
engine IN-PROCESS (the one deliberate exception to the external-CLI rule,
because call counting requires a profiler in the same interpreter) but only
through the public CLI entry point, never internal APIs.

Counted seams (matched by function name + file suffix, so the counts survive
internal moves):
  - parse_file            (markdown parse of one file)
  - find_markdown_files   (directory walk)
  - classify              (artifact classification)
  - collect_corpus / walk_corpus (corpus traversal)

Usage:
  python workcounts.py --corpus /path/c1k --out results/workcounts-before.json
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import sys
from collections import Counter
from pathlib import Path

SEAMS = {
    "parse_file",
    "find_markdown_files",
    "classify",
    "walk_corpus",
    "collect_corpus",
    "corpus_content_hash",
}


def run_counted(argv: list[str]) -> dict:
    """Run one rac CLI command in-process, counting seam calls."""
    from rac.cli import main as rac_main

    counts: Counter[str] = Counter()

    def profiler(frame, event, arg):
        if event == "call":
            name = frame.f_code.co_name
            if name in SEAMS and "/rac/" in frame.f_code.co_filename:
                counts[name] += 1

    out, err = io.StringIO(), io.StringIO()
    sys.setprofile(profiler)
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                code = rac_main(argv)
            except SystemExit as e:
                code = int(e.code or 0)
    finally:
        sys.setprofile(None)
    return {"argv": argv, "exit": code, "stdout_bytes": len(out.getvalue()),
            "counts": dict(sorted(counts.items()))}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--corpus", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    a = ap.parse_args()

    import generate  # sibling module: deterministic ids/terms

    c = a.corpus
    commands = [
        ["validate", c],
        ["index", c, "--json"],
        ["find", generate.RARE[0], c, "--json"],
        ["find", generate.COMMON[0], c, "--json"],
        ["resolve", generate.artifact_id(500), c, "--json"],
        ["relationships", c, "--validate"],
    ]
    results = [run_counted(argv) for argv in commands]
    scorecard = {"metadata": {"corpus": c, "label": a.label}, "runs": results}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(scorecard, indent=2) + "\n")
    print(json.dumps(scorecard, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
