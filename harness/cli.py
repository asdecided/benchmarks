# SPDX-License-Identifier: Apache-2.0
"""The benchmark entry point every subdir's ``run.py`` delegates to.

Flag surface mirrors ``rac eval`` exactly: ``--check | --update-baseline``,
``--json``, ``--root``, ``--queries``, ``--baseline``, ``--config``. Three
modes (default report / ``--check`` gate / ``--update-baseline``): a clean run
exits 0, the gate exits 1 on regression, and any usage error (missing
baseline, unreadable corpus, malformed queries, no ``rac`` on ``PATH``)
exits 2. ``--update-baseline`` is human-only — CI never passes it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from harness import cases as case_mod
from harness import gate as gate_mod
from harness import scorecard as card_mod
from harness import scoring, tools
from harness.errors import UsageError
from harness.runner import RacRunner

EXIT_OK = 0
EXIT_GATE_FAILED = 1
EXIT_USAGE = 2


def build_parser(benchmark_dir: Path, prog: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Run this benchmark against the rac CLI on PATH; deterministic, "
            "offline scoring (ADR-066)."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Gate the current metrics against the committed baseline (exit 1 on failure).",
    )
    mode.add_argument(
        "--update-baseline",
        action="store_true",
        help="Overwrite the baseline with the current metrics (human-gated; CI never).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit the scorecard JSON instead of the summary."
    )
    parser.add_argument(
        "--root",
        default=str(benchmark_dir / "corpus"),
        help="Fixture corpus directory (default: the benchmark's corpus/).",
    )
    parser.add_argument(
        "--queries",
        default=str(benchmark_dir / "queries.json"),
        help="Query set (default: the benchmark's queries.json).",
    )
    parser.add_argument(
        "--baseline",
        default=str(benchmark_dir / "baseline.json"),
        help="Committed baseline metrics (default: the benchmark's baseline.json).",
    )
    parser.add_argument(
        "--config",
        default=str(benchmark_dir / "config.json"),
        help="Gate config: floors and tolerance (default: the benchmark's config.json).",
    )
    return parser


def run_benchmark(
    benchmark_dir: Path,
    config: case_mod.BenchmarkConfig,
    root: str,
    queries_path: str,
    *,
    generated_at: str | None = None,
    executable: str = "decided",
) -> card_mod.Scorecard:
    """Score every committed case and assemble the scorecard.

    Pure over the scored path: ``generated_at`` (a clock) lands only in
    diagnostic ``metadata``, never in the gated ``metrics``.
    """
    if not Path(root).is_dir():
        raise UsageError(f"corpus not found or not a directory: {root}")
    loaded = case_mod.load_query_set(queries_path, config.tool)
    runner = RacRunner(executable)

    results: list = []
    for case in loaded:
        if config.tool in case_mod.RETRIEVAL_TOOLS:
            results.append(tools.run_retrieval_case(runner, root, config.tool, case))
        elif config.tool == case_mod.TOOL_GET_ARTIFACT:
            results.append(tools.run_get_artifact_case(runner, root, case))
        elif config.tool == case_mod.TOOL_GET_RELATED:
            results.append(tools.run_get_related_case(runner, root, case))
        else:
            results.append(tools.run_get_summary_case(runner, root, benchmark_dir, case))

    if config.kind == case_mod.KIND_RETRIEVAL:
        results.sort(key=lambda r: r.case.id)
        metrics = scoring.aggregate_retrieval(results)
    else:
        results.sort(key=lambda r: r.case_id)
        metrics = scoring.aggregate_conformance(results)

    metadata = card_mod.build_metadata(
        rac_version=runner.version(),
        root=root,
        queries_path=queries_path,
        n_queries=len(loaded),
        generated_at=generated_at,
    )
    per_query = [result.to_dict() for result in results]
    return card_mod.Scorecard(metrics=metrics, metadata=metadata, per_query=per_query)


def main(argv: list[str] | None = None, *, benchmark_dir: Path, prog: str = "benchmark") -> int:
    """Run one benchmark subdir; the exit-code contract is 0 / 1 / 2."""
    parser = build_parser(benchmark_dir, prog)
    args = parser.parse_args(argv)
    try:
        config = case_mod.load_config(args.config)
        scorecard = run_benchmark(benchmark_dir, config, args.root, args.queries)
        if args.update_baseline:
            Path(args.baseline).write_text(
                card_mod.render_metrics_json(scorecard.metrics) + "\n", encoding="utf-8"
            )
            print(f"{prog}: baseline updated -> {args.baseline}")
            return EXIT_OK
        if args.check:
            baseline = case_mod.load_baseline(args.baseline)
            gate_config = {"tolerance": config.tolerance, "floors": config.floors}
            failures = gate_mod.evaluate_gate(scorecard.metrics, baseline, gate_config)
            if failures:
                for failure in failures:
                    print(failure.render())
                return EXIT_GATE_FAILED
            print(f"{prog}: gate PASS")
            return EXIT_OK
        if args.json:
            print(card_mod.render_scorecard_json(scorecard))
        else:
            print(card_mod.render_scorecard_human(scorecard, config.kind))
        return EXIT_OK
    except UsageError as exc:
        print(f"{prog}: {exc}", file=sys.stderr)
        return EXIT_USAGE
