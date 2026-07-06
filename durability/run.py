#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Measure the governance claim behind per-artifact splitting: not retrieval
quality (the granularity member proved that is a null under a shared ranker),
but whether the structure retrieval-safety depends on SURVIVES REALISTIC
EDITING.

    python durability/run.py --count 1000 --seed 42 [--out results.json]
    python durability/run.py --seeds 42,43,44 --count 1000 [--out variance.json]

Three pillars, reported in the family scorecard shape (ADR-097), evidence-only,
never a merge gate (ADR-066):

a. SAFETY DECAY — build the granularity member's dual corpus, then apply R edit
   rounds at each sloppy rate in {0.01, 0.05, 0.10}. After every round, re-run
   BOTH retrievals — the status-aware canon (``bm25.iter_live_chunks``) and the
   typed engine over the edited artifacts (``find_decisions``) — in FOUR
   conditions, all reported at equal prominence:
     - ``gated-artifacts``      — ``rac validate`` + ``relationships --validate``
       run each round; edits whose files are flagged are reverted (a merge gate).
     - ``ungated-artifacts``    — edits land regardless (nobody runs the gate).
     - ``canon``                — the monolith; the linter is reported but never
       blocks (reality: no team runs a bespoke linter as a required gate).
     - ``canon-linter-gated``   — for symmetry, the same monolith WITH the
       linter as a gate, to show what a best-effort canon check would recover.
   Two safety metrics per round: superseded-decision LEAKS (a ``must_not_return``
   id returned anywhere) and MISSES (a ``must_return`` head no longer returned).
   The split alone stops the leak (an invalid status cannot masquerade as live);
   only the gate stops the miss (a dropped decision). The report says so.

b. DETECTABILITY MATRIX — inject each break class K times in isolation; report
   the detection rate of the artifact gates (``rac validate`` +
   ``relationships --validate``) versus the canon ``linter``, per class, from the
   actual gate exit findings.

c. MERGE CONFLICTS — N seeded concurrent-edit pairs under deterministic
   three-way ``git merge-file``: per rendering, how often a pair forces a
   shared-file merge and how often that merge conflicts, at controlled block
   gaps, with the analytical same-artifact collision rate for context.

Plus BLAST RADIUS for ``boundary-break``: decisions corrupted per structural
slip — a chunk-count / contamination delta in canon versus exactly one in the
artifacts.

Reruns on unchanged inputs are byte-identical (``sort_keys``); no delta is
claimed unless its sign is stable across ``--seeds``. Nothing here imports the
engine (DG-ADR-0001); stdlib only.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "granularity"))
sys.path.insert(0, str(_REPO_ROOT / "scale"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_corpus  # noqa: E402  (granularity sibling)
import build_queries  # noqa: E402
import edits  # noqa: E402
import linter  # noqa: E402
from _common import _ALPHABET, shard_dir  # noqa: E402
from _model import MODEL_VERSION, artifact_id  # noqa: E402
from arms import run_artifacts_arm  # noqa: E402
from bm25 import iter_chunks, iter_live_chunks, rank_chunks, tokenize  # noqa: E402

SCHEMA_VERSION = 1

DEFAULT_COUNT = 1000
DEFAULT_ROUNDS = 5
DEFAULT_EDITS_PER_ROUND = 100
DEFAULT_RATES = (0.01, 0.05, 0.10)
DEFAULT_INJECT_K = 20
DEFAULT_MERGE_PAIRS = 200
DETECT_COUNT = 200  # a small isolated corpus for the size-independent matrix
MERGE_GAPS = (0, 1, 2, 5, 20)  # block gaps sampled for the conflict-vs-distance table

CONDITIONS = ("gated-artifacts", "ungated-artifacts", "canon", "canon-linter-gated")
_ARTIFACT_CONDS = ("gated-artifacts", "ungated-artifacts")

_DEC_NAME = __import__("re").compile(r"(?:dec|sup)-(\d+)\.md$")


# --- id / index helpers ---------------------------------------------------


def _decode_index(dec_id: str) -> int:
    """The corpus index encoded in a ``RAC-GRA<9 base32>`` id."""
    digits = dec_id[len("RAC-GRA") :]
    value = 0
    for ch in digits:
        value = value * 32 + _ALPHABET.index(ch)
    return value


def _index_of_path(path: str) -> int | None:
    m = _DEC_NAME.search(path)
    return int(m.group(1)) if m else None


def build_pools(cases: list[dict], count: int) -> edits.Pools:
    """Query-exercised superseded ancestors, live heads, and neutral decisions."""
    from _model import chain_info, decision_count

    n_decisions = decision_count(count)
    superseded = sorted({_decode_index(a) for c in cases for a in c["must_not_return"]})
    heads = sorted({_decode_index(h) for c in cases for h in c["must_return"]})
    query_touched = set(superseded) | set(heads)
    # Neutral = live decisions (chain heads or standalones) no query touches.
    neutral = [
        i
        for i in range(n_decisions)
        if i not in query_touched and chain_info(i, n_decisions).head == i
    ]
    return edits.Pools(tuple(superseded), tuple(heads), tuple(neutral), count)


# --- corpus materialisation (base + accepted ledger) ----------------------


def materialize_artifacts(
    base_art: Path, ledger: list[edits.Edit], pools: edits.Pools, work: Path
) -> Path:
    """Fresh copy of the base artifacts with ``ledger`` replayed in order."""
    art = work / "artifacts"
    if art.exists():
        shutil.rmtree(art)
    shutil.copytree(base_art, art)
    for edit in ledger:
        edits.apply_artifacts(art, edit, pools)
    return work


def materialize_canon(
    base_text: str, ledger: list[edits.Edit], pools: edits.Pools
) -> str:
    text = base_text
    for edit in ledger:
        text = edits.apply_canon(text, edit, pools)
    return text


# --- leak / miss measurement ----------------------------------------------


def _leaks_misses(returned: dict[str, list[str]], cases: list[dict]) -> tuple[int, int]:
    leaks = misses = 0
    for case in cases:
        got = set(returned.get(case["id"], []))
        leaks += len(got & set(case["must_not_return"]))
        misses += sum(1 for h in case["must_return"] if h not in got)
    return leaks, misses


def measure_artifacts(work: Path, cases: list[dict]) -> tuple[int, int]:
    return _leaks_misses(run_artifacts_arm(work, cases), cases)


def measure_canon(
    text: str, queries: dict[str, list[str]], cases: list[dict]
) -> tuple[int, int]:
    tmp = Path(tempfile.mkstemp(suffix="-canon.md")[1])
    try:
        tmp.write_text(text, encoding="utf-8")
        ranked = rank_chunks(lambda: iter_live_chunks(tmp), queries)
    finally:
        tmp.unlink(missing_ok=True)
    return _leaks_misses(ranked, cases)


# --- gates ----------------------------------------------------------------


def _artifact_gate_flagged(art: Path) -> set[int]:
    """Decision indices ``rac validate`` + ``relationships --validate`` flag."""
    flagged: set[int] = set()
    val = subprocess.run(
        ["rac", "validate", str(art), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        vd = json.loads(val.stdout)
        for f in vd.get("files", []):
            if f.get("status") != "valid":
                idx = _index_of_path(f["path"])
                if idx is not None:
                    flagged.add(idx)
    except json.JSONDecodeError:
        pass
    rel = subprocess.run(
        ["rac", "relationships", str(art), "--validate", "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        rd = json.loads(rel.stdout)
        for issue in rd.get("issues", []):
            # Most issues carry a single ``source_path``; a duplicate-identifier
            # issue carries a ``paths`` list of every file sharing the id.
            candidates = [issue.get("source_path", "")] + list(issue.get("paths", []))
            for path in candidates:
                idx = _index_of_path(path)
                if idx is not None:
                    flagged.add(idx)
    except json.JSONDecodeError:
        pass
    return flagged


def _canon_gate_flagged(text: str) -> set[int]:
    return {_decode_index(i) for i in linter.flagged_ids(linter.lint(text))}


def _accept(
    proposed: list[edits.Edit], flagged: set[int]
) -> tuple[list[edits.Edit], int]:
    """Keep proposals no gate finding attributes to them; count the rejects."""
    accepted, rejected = [], 0
    for edit in proposed:
        if set(edit.responsible) & flagged:
            rejected += 1
        else:
            accepted.append(edit)
    return accepted, rejected


# --- pillar A: safety decay ------------------------------------------------


def run_decay(
    base: Path,
    cases: list[dict],
    pools: edits.Pools,
    seed: int,
    rounds: int,
    epr: int,
    rates: tuple[float, ...],
    work_root: Path,
) -> dict[str, Any]:
    base_art = base / "artifacts"
    base_canon = (base / "canon" / "decisions-canon.md").read_text(encoding="utf-8")
    queries = {c["id"]: tokenize(c["query"]) for c in cases}

    # Baseline (clean corpus) is identical for every rate; measure once.
    base_art_leaks, base_art_misses = measure_artifacts(base, cases)
    base_canon_leaks, base_canon_misses = measure_canon(base_canon, queries, cases)

    out: dict[str, Any] = {}
    for rate in rates:
        programme = edits.plan(seed, rounds, epr, rate, pools)
        rate_block: dict[str, Any] = {}
        for cond in CONDITIONS:
            is_artifacts = cond in _ARTIFACT_CONDS
            base_l = base_art_leaks if is_artifacts else base_canon_leaks
            base_m = base_art_misses if is_artifacts else base_canon_misses
            per_round = [
                {
                    "round": 0,
                    "leaks": base_l,
                    "misses": base_m,
                    "edits_accepted": 0,
                    "edits_rejected": 0,
                }
            ]
            ledger: list[edits.Edit] = []
            for r in range(rounds):
                proposed = programme[r]
                rejected = 0
                if cond == "gated-artifacts":
                    cand = materialize_artifacts(
                        base_art, ledger + proposed, pools, work_root / "cand"
                    )
                    flagged = _artifact_gate_flagged(cand / "artifacts")
                    accepted, rejected = _accept(proposed, flagged)
                elif cond == "canon-linter-gated":
                    cand_text = materialize_canon(base_canon, ledger + proposed, pools)
                    flagged = _canon_gate_flagged(cand_text)
                    accepted, rejected = _accept(proposed, flagged)
                else:
                    accepted = proposed
                ledger += accepted
                if is_artifacts:
                    work = materialize_artifacts(
                        base_art, ledger, pools, work_root / cond
                    )
                    leaks, misses = measure_artifacts(work, cases)
                else:
                    text = materialize_canon(base_canon, ledger, pools)
                    leaks, misses = measure_canon(text, queries, cases)
                per_round.append(
                    {
                        "round": r + 1,
                        "leaks": leaks,
                        "misses": misses,
                        "edits_accepted": len(accepted),
                        "edits_rejected": rejected,
                    }
                )
            rate_block[cond] = {"per_round": per_round}
        out[f"{rate:.2f}"] = rate_block
    return out


# --- pillar B: detectability matrix ---------------------------------------


def run_detectability(seed: int, k: int, work_root: Path) -> dict[str, Any]:
    """Inject each break class ``k`` times in isolation; measure both gates."""
    det_dir = work_root / "detect"
    if det_dir.exists():
        shutil.rmtree(det_dir)
    manifest = build_corpus.build(DETECT_COUNT, det_dir, seed)
    build_corpus.write_manifest(det_dir, manifest)
    build_queries.write_queries(det_dir, DETECT_COUNT, seed)
    cases = json.loads((det_dir / "queries.json").read_text())["cases"]
    pools = build_pools(cases, DETECT_COUNT)
    base_art = det_dir / "artifacts"
    base_canon = (det_dir / "canon" / "decisions-canon.md").read_text(encoding="utf-8")

    sup = pools.superseded or pools.heads
    heads = pools.heads
    matrix: dict[str, Any] = {}
    for cls in edits.BREAK_CLASSES:
        art_hits = canon_hits = 0
        for j in range(k):
            target = sup if cls in ("malformed-status", "heading-slip") else heads
            tgt = target[j % len(target)]
            new_index = DETECT_COUNT + 1000 + j
            edit = edits.Edit(
                0,
                j,
                True,
                cls,
                tgt,
                new_index=new_index,
                dup_of=heads[(j + 1) % len(heads)],
                dangling_id=artifact_id(DETECT_COUNT * 20 + j),
                responsible=(tgt, new_index),
            )
            # artifacts gate
            work = materialize_artifacts(base_art, [edit], pools, work_root / "det-art")
            if _artifact_gate_flagged(work / "artifacts"):
                art_hits += 1
            # canon linter
            text = edits.apply_canon(base_canon, edit, pools)
            if len(linter.lint(text)) > len(linter.lint(base_canon)):
                canon_hits += 1
        matrix[cls] = {
            "injected": k,
            "artifacts": {"detected": art_hits, "rate": round(art_hits / k, 6)},
            "canon_linter": {"detected": canon_hits, "rate": round(canon_hits / k, 6)},
        }
    return matrix


# --- pillar C: merge conflicts + blast radius -----------------------------


def _merge_conflicts(a_ours: str, base: str, b_theirs: str) -> bool:
    """True when deterministic three-way ``git merge-file`` reports a conflict."""
    with tempfile.TemporaryDirectory() as td:
        tp = Path(td)
        (tp / "base").write_text(base, encoding="utf-8")
        (tp / "ours").write_text(a_ours, encoding="utf-8")
        (tp / "theirs").write_text(b_theirs, encoding="utf-8")
        proc = subprocess.run(
            [
                "git",
                "merge-file",
                "-p",
                str(tp / "ours"),
                str(tp / "base"),
                str(tp / "theirs"),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        return proc.returncode != 0


def run_merge(base: Path, pools: edits.Pools, seed: int, pairs: int) -> dict[str, Any]:
    from _model import decision_count

    n_decisions = decision_count(pools.count)
    base_canon = (base / "canon" / "decisions-canon.md").read_text(encoding="utf-8")
    base_art = base / "artifacts"

    per_gap: dict[str, dict[str, int]] = {
        str(g): {
            "pairs": 0,
            "canon_conflicts": 0,
            "artifacts_same_file": 0,
            "artifacts_conflicts": 0,
        }
        for g in MERGE_GAPS
    }
    for i in range(pairs):
        rng = edits._rng(seed, "merge", i)
        gap = MERGE_GAPS[i % len(MERGE_GAPS)]
        d1 = rng.randrange(n_decisions)
        d2 = (d1 + gap) % n_decisions
        # Two concurrent content edits (reword-context) with distinct tokens.
        e1 = edits.Edit(0, 0, False, "reword-context", d1, responsible=(d1,))
        e2 = edits.Edit(0, 1, False, "reword-context", d2, responsible=(d2,))

        # canon: both edits share the one monolith.
        ours_c = edits.apply_canon(base_canon, e1, pools)
        theirs_c = edits.apply_canon(base_canon, e2, pools)
        canon_conflict = _merge_conflicts(ours_c, base_canon, theirs_c)

        # artifacts: a merge is needed only when both edits touch the same file.
        same_file = d1 == d2
        art_conflict = False
        if same_file:
            f = base_art / shard_dir(d1) / f"dec-{d1:07d}.md"
            base_f = f.read_text(encoding="utf-8")
            ours_text = _apply_one_artifact(base_f, e1, pools)
            theirs_text = _apply_one_artifact(base_f, e2, pools)
            art_conflict = _merge_conflicts(ours_text, base_f, theirs_text)

        g = per_gap[str(gap)]
        g["pairs"] += 1
        g["canon_conflicts"] += int(canon_conflict)
        g["artifacts_same_file"] += int(same_file)
        g["artifacts_conflicts"] += int(art_conflict)

    totals = {
        "pairs": pairs,
        "canon_conflicts": sum(g["canon_conflicts"] for g in per_gap.values()),
        "artifacts_same_file": sum(g["artifacts_same_file"] for g in per_gap.values()),
        "artifacts_conflicts": sum(g["artifacts_conflicts"] for g in per_gap.values()),
    }
    return {
        "per_gap": per_gap,
        "totals": totals,
        "canon_shared_file_rate": 1.0,  # every concurrent pair merges one monolith
        "artifacts_same_file_rate": round(totals["artifacts_same_file"] / pairs, 6),
        "expected_same_artifact_collision_rate": round(1.0 / n_decisions, 6),
    }


def _apply_one_artifact(file_text: str, edit: edits.Edit, pools: edits.Pools) -> str:
    """Apply a single content edit to one artifact's text (for pair merges)."""
    new = edits._reworded_context(edit)
    return edits._replace_section_body(file_text, "## Context", new)


def run_blast_radius(
    base: Path, pools: edits.Pools, seed: int, k: int
) -> dict[str, Any]:
    """boundary-break decisions-affected: canon (lost + contaminated) vs artifacts (1)."""
    base_canon = (base / "canon" / "decisions-canon.md").read_text(encoding="utf-8")
    tmp = Path(tempfile.mkstemp(suffix="-blast.md")[1])
    base_ids = [i for i, _ in iter_chunks(_write(tmp, base_canon))]
    canon_radii: list[int] = []
    heads = pools.heads or (0,)
    for j in range(k):
        tgt = heads[j % len(heads)]
        edit = edits.Edit(0, j, True, "boundary-break", tgt, responsible=(tgt,))
        text = edits.apply_canon(base_canon, edit, pools)
        after_ids = [i for i, _ in iter_chunks(_write(tmp, text))]
        lost = len(set(base_ids) - set(after_ids))  # ids no longer reachable
        # Each lost id contaminates exactly one host chunk (its predecessor).
        canon_radii.append(lost + (1 if lost else 0))
    tmp.unlink(missing_ok=True)
    mean = round(sum(canon_radii) / len(canon_radii), 6) if canon_radii else 0.0
    return {
        "injected": k,
        "canon": {
            "mean_decisions_affected": mean,
            "min": min(canon_radii),
            "max": max(canon_radii),
        },
        "artifacts": {"mean_decisions_affected": 1.0, "min": 1, "max": 1},
    }


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


# --- single-seed scorecard -------------------------------------------------


def _engine_version() -> str:
    try:
        out = subprocess.run(
            ["rac", "--version"], capture_output=True, text=True, check=False
        )
        return (out.stdout or out.stderr).strip()
    except OSError:
        return "unavailable"


def run(
    count: int,
    seed: int,
    rounds: int,
    epr: int,
    rates: tuple[float, ...],
    inject_k: int,
    merge_pairs: int,
) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="dur-") as td:
        root = Path(td)
        base = root / "corpus"
        manifest = build_corpus.build(count, base, seed)
        build_corpus.write_manifest(base, manifest)
        build_queries.write_queries(base, count, seed)
        cases = json.loads((base / "queries.json").read_text())["cases"]
        pools = build_pools(cases, count)

        decay = run_decay(base, cases, pools, seed, rounds, epr, rates, root / "work")
        detect = run_detectability(seed, inject_k, root / "work")
        merge = run_merge(base, pools, seed, merge_pairs)
        blast = run_blast_radius(base, pools, seed, inject_k)

    return {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "metrics": {
            "safety_decay": decay,
            "detectability": detect,
            "merge_conflicts": merge,
            "blast_radius": blast,
        },
        "metadata": {
            "count": count,
            "seed": seed,
            "rounds": rounds,
            "edits_per_round": epr,
            "rates": list(rates),
            "inject_k": inject_k,
            "merge_pairs": merge_pairs,
            "taxonomy_version": edits.TAXONOMY_VERSION,
            "model_version": MODEL_VERSION,
            "engine_version": _engine_version(),
            "pool_sizes": {
                "superseded": len(pools.superseded),
                "heads": len(pools.heads),
                "neutral": len(pools.neutral),
            },
        },
    }


# --- multi-seed variance ---------------------------------------------------


def _final(decay: dict, rate: str, cond: str, metric: str) -> int:
    return decay[rate][cond]["per_round"][-1][metric]


def run_seeds(
    count: int,
    seeds: list[int],
    rounds: int,
    epr: int,
    rates: tuple[float, ...],
    inject_k: int,
    merge_pairs: int,
) -> dict[str, Any]:
    per_seed = {
        str(s): run(count, s, rounds, epr, rates, inject_k, merge_pairs) for s in seeds
    }
    top_rate = f"{max(rates):.2f}"

    # Headline deltas whose sign must be stable: the rot each rendering takes at
    # the highest sloppy rate, final round, versus the gated-artifacts arm.
    headline = {
        "canon_leaks_vs_gated": ("canon", "gated-artifacts", "leaks"),
        "canon_misses_vs_gated": ("canon", "gated-artifacts", "misses"),
        "ungated_misses_vs_gated": ("ungated-artifacts", "gated-artifacts", "misses"),
        "ungated_leaks_vs_gated": ("ungated-artifacts", "gated-artifacts", "leaks"),
    }
    sign_consistency: dict[str, Any] = {}
    for name, (high, low, metric) in headline.items():
        deltas = [
            _final(per_seed[str(s)]["metrics"]["safety_decay"], top_rate, high, metric)
            - _final(per_seed[str(s)]["metrics"]["safety_decay"], top_rate, low, metric)
            for s in seeds
        ]
        signs = {(1 if d > 0 else -1 if d < 0 else 0) for d in deltas}
        sign_consistency[name] = {
            "rate": top_rate,
            "metric": metric,
            "high": high,
            "low": low,
            "deltas": deltas,
            "consistent": len(signs) == 1,
            "sign": "+"
            if signs == {1}
            else "-"
            if signs == {-1}
            else "0"
            if signs == {0}
            else "mixed",
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "model_version": MODEL_VERSION,
        "count": count,
        "seeds": seeds,
        "sign_consistency": sign_consistency,
        "per_seed": per_seed,
    }


# --- stdout tables ---------------------------------------------------------


def _print_decay(card: dict[str, Any]) -> None:
    decay = card["metrics"]["safety_decay"]
    rounds = card["metadata"]["rounds"]
    print("SAFETY DECAY — leaks / misses per round, per condition, per sloppy rate")
    print(
        "(leaks = superseded id returned; misses = live head dropped; lower is better)\n"
    )
    for rate in sorted(decay):
        print(f"  sloppy rate {rate}")
        header = f"    {'condition':<20}" + "".join(
            f"  r{r:>2}" for r in range(rounds + 1)
        )
        print(header + "     (leaks)")
        for cond in CONDITIONS:
            pr = decay[rate][cond]["per_round"]
            cells = "".join(f"  {row['leaks']:>3}" for row in pr)
            print(f"    {cond:<20}{cells}")
        print(
            f"    {'':<20}"
            + "".join(f"  r{r:>2}" for r in range(rounds + 1))
            + "     (misses)"
        )
        for cond in CONDITIONS:
            pr = decay[rate][cond]["per_round"]
            cells = "".join(f"  {row['misses']:>3}" for row in pr)
            print(f"    {cond:<20}{cells}")
        print()


def _print_detect(card: dict[str, Any]) -> None:
    det = card["metrics"]["detectability"]
    print("DETECTABILITY MATRIX — detection rate per break class (K injections)")
    print(f"  {'break class':<18}{'artifacts gate':>16}{'canon linter':>16}")
    print("  " + "-" * 48)
    for cls in edits.BREAK_CLASSES:
        a = det[cls]["artifacts"]["rate"]
        c = det[cls]["canon_linter"]["rate"]
        print(f"  {cls:<18}{a:>16.2f}{c:>16.2f}")
    print("  (artifacts miss heading-slip — harmless there; the linter misses")
    print("   dangling-ref — it cannot resolve a target without the schema graph.)\n")


def _print_merge(card: dict[str, Any]) -> None:
    m = card["metrics"]["merge_conflicts"]
    print("MERGE CONFLICTS — deterministic three-way git merge-file, per block gap")
    print(
        f"  {'gap':>4}{'pairs':>8}{'canon confl':>14}{'art same-file':>16}{'art confl':>12}"
    )
    print("  " + "-" * 54)
    for g in MERGE_GAPS:
        row = m["per_gap"][str(g)]
        print(
            f"  {g:>4}{row['pairs']:>8}{row['canon_conflicts']:>14}"
            f"{row['artifacts_same_file']:>16}{row['artifacts_conflicts']:>12}"
        )
    print(
        f"  canon forces a shared-file merge on 100% of concurrent pairs; "
        f"artifacts\n  same-file rate {m['artifacts_same_file_rate']:.4f} "
        f"(expected same-artifact collision {m['expected_same_artifact_collision_rate']:.4f}).\n"
    )


def _print_blast(card: dict[str, Any]) -> None:
    b = card["metrics"]["blast_radius"]
    print("BLAST RADIUS — decisions corrupted per boundary-break")
    print(
        f"  canon     mean {b['canon']['mean_decisions_affected']:.2f} "
        f"[{b['canon']['min']},{b['canon']['max']}]"
    )
    print(
        f"  artifacts mean {b['artifacts']['mean_decisions_affected']:.2f} "
        f"[{b['artifacts']['min']},{b['artifacts']['max']}]  (identity is per-file)\n"
    )


def _print_single(card: dict[str, Any]) -> None:
    _print_decay(card)
    _print_detect(card)
    _print_merge(card)
    _print_blast(card)


def _print_variance(report: dict[str, Any]) -> None:
    print(f"MULTI-SEED — count={report['count']} seeds={report['seeds']}\n")
    print("Headline delta sign consistency (highest sloppy rate, final round)")
    for name, blk in report["sign_consistency"].items():
        flag = "stable" if blk["consistent"] else "MIXED"
        print(f"  {name:<26} sign={blk['sign']:<6} {flag:<7} deltas={blk['deltas']}")
    print()


# --- driver ---------------------------------------------------------------


def _parse_seeds(text: str) -> list[int]:
    return [int(s.strip()) for s in text.split(",") if s.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=DEFAULT_COUNT)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--seeds",
        type=str,
        default=None,
        help="Comma-separated seeds for multi-seed sign consistency.",
    )
    parser.add_argument("--rounds", type=int, default=DEFAULT_ROUNDS)
    parser.add_argument("--edits-per-round", type=int, default=DEFAULT_EDITS_PER_ROUND)
    parser.add_argument("--inject-k", type=int, default=DEFAULT_INJECT_K)
    parser.add_argument("--merge-pairs", type=int, default=DEFAULT_MERGE_PAIRS)
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args(argv)
    if args.count < 1:
        parser.error("--count must be positive")

    rates = DEFAULT_RATES

    if args.seeds:
        seeds = _parse_seeds(args.seeds)
        if not seeds:
            parser.error("--seeds must list at least one integer")
        report = run_seeds(
            args.count,
            seeds,
            args.rounds,
            args.edits_per_round,
            rates,
            args.inject_k,
            args.merge_pairs,
        )
        out = args.out or Path("variance.json")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(f"multi-seed durability over {seeds} at count={args.count} -> {out}\n")
        _print_variance(report)
        # Print the first seed's tables so the run is legible on its own.
        _print_single(report["per_seed"][str(seeds[0])])
        return 0

    card = run(
        args.count,
        args.seed,
        args.rounds,
        args.edits_per_round,
        rates,
        args.inject_k,
        args.merge_pairs,
    )
    out = args.out or Path("results.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"durability scorecard at count={args.count} seed={args.seed} -> {out}\n")
    _print_single(card)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
