#!/usr/bin/env python3
"""Source-quality census for the rebuild evidence: complexity, maintainability,
LOC, duplication, typing, and docstring/comment coverage of a Python tree.

Pure static analysis — no engine imports. Emits one JSON scorecard so the
before/after runs diff cleanly.

Usage:
  python srcmetrics.py --src /path/to/rac-core/src/rac --out results/src-before.json
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import subprocess
import sys
import tokenize
from pathlib import Path


def loc_census(files: list[Path]) -> dict:
    total = code = blank = comment = 0
    for f in files:
        for line in f.read_text(encoding="utf-8", errors="replace").splitlines():
            total += 1
            s = line.strip()
            if not s:
                blank += 1
            elif s.startswith("#"):
                comment += 1
            else:
                code += 1
    return {"files": len(files), "total_lines": total, "code_lines": code,
            "comment_lines": comment, "blank_lines": blank}


def docstring_census(files: list[Path]) -> dict:
    """AST census: how many modules/classes/functions carry docstrings, and
    how many function defs are fully annotated."""
    counts = {"modules": 0, "modules_doc": 0, "classes": 0, "classes_doc": 0,
              "functions": 0, "functions_doc": 0,
              "functions_fully_annotated": 0}
    for f in files:
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        counts["modules"] += 1
        counts["modules_doc"] += int(ast.get_docstring(tree) is not None)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                counts["classes"] += 1
                counts["classes_doc"] += int(ast.get_docstring(node) is not None)
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                counts["functions"] += 1
                counts["functions_doc"] += int(ast.get_docstring(node) is not None)
                args = node.args
                all_args = args.posonlyargs + args.args + args.kwonlyargs
                relevant = [a for a in all_args if a.arg not in ("self", "cls")]
                annotated = all(a.annotation is not None for a in relevant)
                if annotated and node.returns is not None:
                    counts["functions_fully_annotated"] += 1
    return counts


def radon_metrics(src: Path) -> dict:
    """Cyclomatic complexity + maintainability index via radon's JSON output."""
    cc = json.loads(subprocess.run(
        [sys.executable, "-m", "radon", "cc", "-s", "-j", str(src)],
        capture_output=True, text=True).stdout)
    blocks = [b for file_blocks in cc.values() for b in file_blocks if isinstance(b, dict)]
    complexities = sorted((b["complexity"] for b in blocks), reverse=True)
    mi = json.loads(subprocess.run(
        [sys.executable, "-m", "radon", "mi", "-j", str(src)],
        capture_output=True, text=True).stdout)
    mi_vals = sorted(v["mi"] for v in mi.values() if isinstance(v, dict))
    return {
        "cc_blocks": len(complexities),
        "cc_total": sum(complexities),
        "cc_mean": round(sum(complexities) / len(complexities), 2) if complexities else 0,
        "cc_max": complexities[0] if complexities else 0,
        "cc_blocks_over_10": sum(1 for c in complexities if c > 10),
        "mi_files": len(mi_vals),
        "mi_mean": round(sum(mi_vals) / len(mi_vals), 1) if mi_vals else 0,
        "mi_min": round(mi_vals[0], 1) if mi_vals else 0,
        "mi_files_under_65": sum(1 for v in mi_vals if v < 65),
    }


def duplication(src: Path) -> dict:
    """Duplicate-code blocks via pylint's similarity checker (8-line window)."""
    proc = subprocess.run(
        [sys.executable, "-m", "pylint", "--disable=all", "--enable=duplicate-code",
         "--min-similarity-lines=8", "--recursive=y", str(src)],
        capture_output=True, text=True)
    import re

    dup_blocks = proc.stdout.count("R0801")
    dup_lines = sum(
        int(m.group(2)) - int(m.group(1))
        for m in re.finditer(r"==\S+:\[(\d+):(\d+)\]", proc.stdout)
    )
    return {"duplicate_blocks": dup_blocks, "duplicate_line_span": dup_lines,
            "min_similarity_lines": 8}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--label", default="")
    a = ap.parse_args()
    src = Path(a.src)
    files = sorted(p for p in src.rglob("*.py") if "__pycache__" not in p.parts)
    scorecard = {
        "metadata": {"src": str(src), "label": a.label},
        "loc": loc_census(files),
        "docstrings": docstring_census(files),
        "radon": radon_metrics(src),
        "duplication": duplication(src),
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(scorecard, indent=2) + "\n")
    print(json.dumps(scorecard, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
