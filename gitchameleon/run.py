#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Entry point for the GitChameleon evidence run.

Offline (no model calls, no spend):

- ``--dry-run`` assembles the per-example, per-arm prompt bundles — task
  prompt plus the arm's grounding context — and writes them as JSONL, so the
  grounding seam is inspectable and testable offline.

The funded-run pipeline (GCB-ADR-0002) is three further modes, each usable in
isolation so a funded session can resume anywhere:

- ``solutions`` — feed each dry-run bundle to the answering model and write
  per-arm solution JSONL in the exact shape the upstream harness's
  ``evaluate --solution-path`` consumes ({"example_id", "answer", ...extras});
  the ``offline-stub`` backend exercises the plumbing keylessly.
- ``score`` — normalize one arm's upstream ``*_eval_results.csv`` (the
  executable-test verdicts; we add NO scorer) into per-(example, arm) paired
  resolution records (schema/resolution_record.schema.json).
- ``stats`` — run the pre-registered paired analysis (exact McNemar, effect
  sizes; decisiongrounding/scoring/stats.py) over the resolution records with
  ``passed`` as the outcome.

This is an EVIDENCE RUN, not a merge gate: scoring belongs to the upstream
GitChameleon harness (executable tests), and results are labelled with the
upstream pin (dataset/provenance.json). See README.md.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

BENCHMARK_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCHMARK_DIR.parent))

import arms as arms_mod

from harness.runner import RacRunner

EXIT_OK = 0
EXIT_USAGE = 2


def load_rows(dataset_path: Path) -> list[dict]:
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    return payload["rows"] if isinstance(payload, dict) else payload


def _dataset_revision(provenance_path: Path) -> str | None:
    if provenance_path.is_file():
        return json.loads(provenance_path.read_text(encoding="utf-8")).get("revision")
    return None


def _prompt_hash(bundle: dict) -> str:
    return hashlib.sha256(bundle["prompt"].encode("utf-8")).hexdigest()


def _grounding_hash(bundle: dict) -> str:
    grounding = bundle.get("grounding") or []
    return hashlib.sha256(
        json.dumps(grounding, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def dry_run(
    rows: list[dict], corpus_root: Path, arm_names: list[str], out_path: Path
) -> int:
    runner = RacRunner() if "asdecided" in arm_names else None
    embedder = arms_mod.VoyageEmbedder() if "naive_rag" in arm_names else None
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
                grounding = arms_mod.assemble_grounding(
                    arm, runner, corpus_dir, row, embedder=embedder
                )
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


def cmd_solutions(args) -> int:
    """Bundles -> per-arm solution JSONL in the upstream harness's shape."""
    from answer import make_answering_model

    bundles_path = Path(args.bundles)
    if not bundles_path.is_file():
        print(
            f"gitchameleon: bundles not found: {bundles_path} — run --dry-run first",
            file=sys.stderr,
        )
        return EXIT_USAGE
    if args.resume and args.overwrite:
        print(
            "gitchameleon: --resume and --overwrite are mutually exclusive",
            file=sys.stderr,
        )
        return EXIT_USAGE
    requested_arms = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
    unknown = [arm for arm in requested_arms if arm not in arms_mod.ARMS]
    if unknown:
        print(
            f"gitchameleon: unknown arm(s) {unknown}; expected {arms_mod.ARMS}",
            file=sys.stderr,
        )
        return EXIT_USAGE

    bundles = [
        json.loads(line)
        for line in bundles_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    bundles = [bundle for bundle in bundles if bundle["arm"] in requested_arms]
    if args.limit is not None:
        per_arm: dict[str, int] = {}
        limited: list[dict] = []
        for bundle in bundles:
            arm = bundle["arm"]
            if per_arm.get(arm, 0) >= args.limit:
                continue
            limited.append(bundle)
            per_arm[arm] = per_arm.get(arm, 0) + 1
        bundles = limited
    if not bundles:
        print("gitchameleon: no bundles selected", file=sys.stderr)
        return EXIT_USAGE

    model = make_answering_model(args.answering, args.seed)
    revision = _dataset_revision(Path(args.provenance))
    if revision is None:
        print(
            f"gitchameleon: warning — no dataset provenance at {args.provenance}; "
            "the records will carry dataset_revision=null",
            file=sys.stderr,
        )

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    selected_arms = sorted({bundle["arm"] for bundle in bundles})
    bundle_by_key = {
        (bundle["arm"], str(bundle["example_id"])): bundle for bundle in bundles
    }
    completed: dict[str, set[str]] = {arm: set() for arm in selected_arms}
    for arm in selected_arms:
        path = out_dir / f"solutions-{arm}.jsonl"
        if not path.exists():
            continue
        if not args.resume and not args.overwrite:
            print(
                f"gitchameleon: refusing to overwrite {path}; pass --resume or --overwrite",
                file=sys.stderr,
            )
            return EXIT_USAGE
        if args.resume:
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    print(
                        f"gitchameleon: invalid resume record {path}:{line_number}: {exc}",
                        file=sys.stderr,
                    )
                    return EXIT_USAGE
                record_key = (arm, str(record["example_id"]))
                bundle = bundle_by_key.get(record_key)
                expected = {
                    "answering_model": model.version,
                    "seed": args.seed,
                    "dataset_revision": revision,
                    "prompt_sha256": _prompt_hash(bundle) if bundle else None,
                    "grounding_sha256": _grounding_hash(bundle) if bundle else None,
                }
                mismatched = {
                    field: {"found": record.get(field), "expected": value}
                    for field, value in expected.items()
                    if record.get(field) != value
                }
                if mismatched:
                    print(
                        f"gitchameleon: cannot resume incompatible record "
                        f"{path}:{line_number}: {mismatched}",
                        file=sys.stderr,
                    )
                    return EXIT_USAGE
                completed[arm].add(str(record["example_id"]))

    handles: dict[str, object] = {}
    counts: dict[str, int] = {}
    skipped: dict[str, int] = {}
    try:
        for bundle in bundles:
            arm = bundle["arm"]
            example_id = str(bundle["example_id"])
            if example_id in completed[arm]:
                skipped[arm] = skipped.get(arm, 0) + 1
                continue
            grounding = bundle.get("grounding") or []
            answer = model.complete(bundle["prompt"], grounding)
            if arm not in handles:
                mode = "a" if args.resume else "w"
                handles[arm] = (out_dir / f"solutions-{arm}.jsonl").open(
                    mode, encoding="utf-8"
                )
            # Upstream Solution reads example_id + answer and ignores extras.
            handles[arm].write(
                json.dumps(
                    {
                        "example_id": example_id,
                        "answer": answer,
                        "arm": arm,
                        "library": bundle.get("library"),
                        "version": bundle.get("version"),
                        "answering_model": model.version,
                        "seed": args.seed,
                        "dataset_revision": revision,
                        "prompt_sha256": _prompt_hash(bundle),
                        "grounding_sha256": _grounding_hash(bundle),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            handles[arm].flush()
            counts[arm] = counts.get(arm, 0) + 1
            print(f"answered {arm} example {example_id}", file=sys.stderr)
    finally:
        for h in handles.values():
            h.close()
    for arm in selected_arms:
        n = counts.get(arm, 0)
        already = skipped.get(arm, 0)
        print(
            f"wrote {n} solutions ({already} resumed) -> "
            f"{out_dir / f'solutions-{arm}.jsonl'}"
        )
    print(
        "score each file with the upstream harness: "
        "evaluate --solution-path <file>  (GitChameleonBenchmark)"
    )
    return EXIT_OK


def _truthy(value: str) -> bool:
    return str(value).strip().lower() in ("true", "1", "yes")


def cmd_score(args) -> int:
    """One arm's upstream eval_results CSV -> paired resolution records."""
    eval_path = Path(args.eval_results)
    if not eval_path.is_file():
        print(f"gitchameleon: eval results not found: {eval_path}", file=sys.stderr)
        return EXIT_USAGE
    by_example: dict[str, dict] = {}
    for row in csv.DictReader(eval_path.open(encoding="utf-8")):
        if row.get("code_id") not in (None, "", "solution_code"):
            continue  # only the hidden-test solution verdicts
        eid = str(row["example_id"])
        by_example[eid] = {
            "example_id": eid,
            "arm": args.arm,
            "passed": _truthy(row.get("passed", "")),
            "compiled": _truthy(row["compiled"])
            if row.get("compiled") not in (None, "")
            else None,
            "answering_model": args.answering_model,
            "seed": args.seed,
            "dataset_revision": args.dataset_revision
            or _dataset_revision(Path(args.provenance)),
            "upstream_harness": args.upstream_harness,
        }
    if not by_example:
        print(
            "gitchameleon: no solution_code rows found in the eval CSV", file=sys.stderr
        )
        return EXIT_USAGE
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.append else "w"
    with out_path.open(mode, encoding="utf-8") as out:
        for eid in sorted(by_example, key=int):
            out.write(json.dumps(by_example[eid], ensure_ascii=False) + "\n")
    passed = sum(1 for r in by_example.values() if r["passed"])
    print(
        f"{args.arm}: {passed}/{len(by_example)} passed -> {out_path}"
        f" ({'appended' if args.append else 'wrote'})"
    )
    return EXIT_OK


def cmd_stats(args) -> int:
    """The pre-registered paired analysis over resolution records."""
    records_path = Path(args.records)
    if not records_path.is_file():
        print(f"gitchameleon: records not found: {records_path}", file=sys.stderr)
        return EXIT_USAGE
    sys.path.insert(0, str(BENCHMARK_DIR.parent / "decisiongrounding"))
    from scoring.stats import paired_significance

    records = [
        json.loads(line)
        for line in records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    required_arms = [arm.strip() for arm in args.require_arms.split(",") if arm.strip()]
    by_arm: dict[str, set[str]] = {}
    seen: set[tuple[str, str, object]] = set()
    for record in records:
        key = (record["arm"], str(record["example_id"]), record.get("seed"))
        if key in seen:
            print(f"gitchameleon: duplicate resolution record {key}", file=sys.stderr)
            return EXIT_USAGE
        seen.add(key)
        by_arm.setdefault(record["arm"], set()).add(str(record["example_id"]))
    missing_arms = [arm for arm in required_arms if arm not in by_arm]
    if missing_arms:
        print(
            f"gitchameleon: required arm(s) missing from records: {missing_arms}",
            file=sys.stderr,
        )
        return EXIT_USAGE
    compared = required_arms or sorted(by_arm)
    if len(compared) < 2:
        print("gitchameleon: stats needs at least two arms", file=sys.stderr)
        return EXIT_USAGE
    expected = by_arm[compared[0]]
    incomplete = {
        arm: sorted(expected.symmetric_difference(by_arm[arm]), key=int)
        for arm in compared[1:]
        if by_arm[arm] != expected
    }
    if incomplete:
        print(f"gitchameleon: incomplete paired records: {incomplete}", file=sys.stderr)
        return EXIT_USAGE
    out = paired_significance(records, outcome="passed")
    rendered = json.dumps(out, indent=2)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
        print(f"wrote {args.out}")
    else:
        print(rendered)
    return EXIT_OK


def _add_common_provenance(sub) -> None:
    sub.add_argument(
        "--provenance",
        default=str(BENCHMARK_DIR / "dataset" / "provenance.json"),
        help="fetch_dataset.py provenance pin (for dataset_revision).",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="gitchameleon",
        description="GitChameleon evidence run: dry-run offline; "
        "solutions/score/stats are the funded-run pipeline.",
    )
    sub = parser.add_subparsers(dest="mode")

    p_sol = sub.add_parser(
        "solutions", help="answer each bundle; write per-arm solution JSONL"
    )
    p_sol.add_argument(
        "--bundles", default=str(BENCHMARK_DIR / "out" / "bundles.jsonl")
    )
    p_sol.add_argument(
        "--answering",
        default="offline-stub",
        help="offline-stub | claude | litellm:<alias>",
    )
    p_sol.add_argument(
        "--arms",
        default=",".join(arms_mod.ARMS),
        help="comma-separated subset of arms to answer",
    )
    p_sol.add_argument(
        "--limit",
        type=int,
        default=None,
        help="answer at most N examples per selected arm (shakedowns only)",
    )
    p_sol.add_argument(
        "--resume",
        action="store_true",
        help="append only missing example ids to existing arm files",
    )
    p_sol.add_argument(
        "--overwrite",
        action="store_true",
        help="replace existing selected-arm solution files",
    )
    p_sol.add_argument("--seed", type=int, default=0)
    p_sol.add_argument("--out", default=str(BENCHMARK_DIR / "out" / "solutions"))
    _add_common_provenance(p_sol)
    p_sol.set_defaults(func=cmd_solutions)

    p_score = sub.add_parser(
        "score",
        help="normalize an upstream eval_results CSV into paired resolution records",
    )
    p_score.add_argument("--arm", required=True, choices=arms_mod.ARMS)
    p_score.add_argument(
        "--eval-results",
        required=True,
        help="the upstream harness's *_eval_results.csv for this arm",
    )
    p_score.add_argument(
        "--out", default=str(BENCHMARK_DIR / "out" / "resolution_records.jsonl")
    )
    p_score.add_argument(
        "--append", action="store_true", help="append to --out (one file across arms)"
    )
    p_score.add_argument(
        "--answering-model",
        default=None,
        help="the pinned answering model the solutions used",
    )
    p_score.add_argument("--seed", type=int, default=0)
    p_score.add_argument("--dataset-revision", default=None)
    p_score.add_argument(
        "--upstream-harness",
        default=None,
        help="GitChameleonBenchmark commit/tag used to score",
    )
    _add_common_provenance(p_score)
    p_score.set_defaults(func=cmd_score)

    p_stats = sub.add_parser(
        "stats", help="paired significance over resolution records"
    )
    p_stats.add_argument(
        "--records", default=str(BENCHMARK_DIR / "out" / "resolution_records.jsonl")
    )
    p_stats.add_argument(
        "--out", default=None, help="write JSON here instead of stdout"
    )
    p_stats.add_argument(
        "--require-arms",
        default="",
        help="comma-separated arms that must all contain the same example IDs",
    )
    p_stats.set_defaults(func=cmd_stats)

    # Legacy top-level dry-run flags (the offline scaffold surface).
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
        default="no_grounding,asdecided",
        help="Comma-separated arms (naive_rag refuses until its embedder is pinned).",
    )
    parser.add_argument(
        "--out",
        default=str(BENCHMARK_DIR / "out" / "bundles.jsonl"),
        help="Where the dry-run writes the prompt bundles (JSONL).",
    )
    args = parser.parse_args(argv)

    if getattr(args, "mode", None):
        return args.func(args)

    arm_names = [arm.strip() for arm in args.arms.split(",") if arm.strip()]
    unknown = [arm for arm in arm_names if arm not in arms_mod.ARMS]
    if unknown:
        print(
            f"gitchameleon: unknown arm(s) {unknown}; expected {arms_mod.ARMS}",
            file=sys.stderr,
        )
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
            "gitchameleon: pass --dry-run for the offline bundles, or one of the "
            "funded-run modes: solutions / score / stats (see README.md, "
            "'The funded run').",
            file=sys.stderr,
        )
        return EXIT_USAGE

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return dry_run(load_rows(dataset_path), Path(args.corpus), arm_names, out_path)
    except (NotImplementedError, ValueError) as exc:
        print(f"gitchameleon: {exc}", file=sys.stderr)
        return EXIT_USAGE


if __name__ == "__main__":
    raise SystemExit(main())
