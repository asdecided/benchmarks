#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Entry point for the GitChameleon evidence-run scaffold.

Scaffold scope (no funded runs): ``--dry-run`` assembles the per-example,
per-arm prompt bundles — task prompt plus the arm's grounding context — and
writes them as JSONL, so the grounding seam is inspectable and testable
offline. The answering-model call and the upstream execution-based scoring
are the funded-run seam and deliberately refuse until then.

This is an EVIDENCE RUN scaffold, not a merge gate: scoring belongs to the
upstream GitChameleon harness (executable tests), and results are labelled
with the upstream pin (dataset/provenance.json). See README.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCHMARK_DIR.parent))

from harness.runner import RacRunner  # noqa: E402

import arms as arms_mod  # noqa: E402

EXIT_OK = 0
EXIT_USAGE = 2


def load_rows(dataset_path: Path) -> list[dict]:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    return payload["rows"] if isinstance(payload, dict) else payload


def dry_run(rows: list[dict], corpus_root: Path, arm_names: list[str], out_path: Path) -> int:
    runner = RacRunner() if "rac" in arm_names else None
    bundles = 0
    with out_path.open("w", encoding="utf-8") as out:
        for row in rows:
            corpus_dir = corpus_root / f"example-{row['example_id']}"
            if not corpus_dir.is_dir():
                print(
                    f"run: no corpus for example {row['example_id']} — "
                    "run build_corpus.py first",
                    file=sys.stderr,
                )
                return EXIT_USAGE
            for arm in arm_names:
                grounding = arms_mod.assemble_grounding(arm, runner, corpus_dir, row)
                out.write(
                    json.dumps(
                        {
                            "example_id": row["example_id"],
                            "arm": arm,
                            "library": row["library"],
                            "version": row["version"],
                            "prompt": arms_mod.task_prompt(row),
                            "grounding": grounding,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
                bundles += 1
    print(f"wrote {bundles} prompt bundles -> {out_path}")
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gitchameleon",
        description="GitChameleon evidence-run scaffold (dry-run only until funded).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Assemble per-example, per-arm prompt bundles without any model call.",
    )
    parser.add_argument(
        "--dataset",
        default=str(BENCHMARK_DIR / "dataset" / "problems.json"),
        help="Problem rows (fetch_dataset.py output, or the committed fixture).",
    )
    parser.add_argument(
        "--corpus",
        default=str(BENCHMARK_DIR / "corpus-build"),
        help="Per-example corpus root (build_corpus.py output).",
    )
    parser.add_argument(
        "--arms",
        default="no_grounding,rac",
        help="Comma-separated arms (naive_rag refuses until its embedder is pinned).",
    )
    parser.add_argument(
        "--out",
        default=str(BENCHMARK_DIR / "out" / "bundles.jsonl"),
        help="Where the dry-run writes the prompt bundles (JSONL).",
    )
    args = parser.parse_args(argv)

    arm_names = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
    unknown = [arm for arm in arm_names if arm not in arms_mod.ARMS]
    if unknown:
        print(f"gitchameleon: unknown arm(s) {unknown}; expected {arms_mod.ARMS}", file=sys.stderr)
        return EXIT_USAGE

    dataset_path = Path(args.dataset)
    if not dataset_path.is_file():
        print(
            f"gitchameleon: dataset not found: {dataset_path} — run fetch_dataset.py "
            "(or point --dataset at fixtures/sample_problems.json)",
            file=sys.stderr,
        )
        return EXIT_USAGE

    if not args.dry_run:
        print(
            "gitchameleon: only --dry-run is implemented in the scaffold. The "
            "answering-model call and upstream execution scoring are the "
            "funded-run seam (see README.md, 'The funded run').",
            file=sys.stderr,
        )
        return EXIT_USAGE

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return dry_run(load_rows(dataset_path), Path(args.corpus), arm_names, out_path)
    except NotImplementedError as exc:
        print(f"gitchameleon: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
