# SPDX-License-Identifier: Apache-2.0
"""Per-tool case execution: drive the CLI surface, hand results to the scorer.

Each Lore MCP tool maps to the CLI surface that serves the same contract:

- ``search_artifacts`` → ``rac find <query> <root> --json [--type T]``
- ``find_decisions``   → ``rac find <query> <root> --decisions --json``
- ``get_artifact``     → ``rac resolve <id> <root> --json``
- ``get_related``      → ``rac relationships <path|root> --json`` (id → path
  resolved via ``rac resolve``; incoming edges derived by inverting the
  corpus-wide relationship map — plumbing, never a re-rank)
- ``get_summary``      → ``rac portfolio <root> --json``

Production output is consumed verbatim: no re-sort, no re-rank, membership
compared by id only.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

from harness.cases import (
    GetArtifactCase,
    GetRelatedCase,
    GetSummaryCase,
    RetrievalCase,
    TOOL_FIND_DECISIONS,
)
from harness.errors import UsageError
from harness.runner import RacRunner
from harness.scoring import Check, ConformanceResult, RetrievalResult, score_retrieval_case


def run_retrieval_case(
    runner: RacRunner, root: str, tool: str, case: RetrievalCase
) -> RetrievalResult:
    """One ranked-retrieval case: production order in, scored row out."""
    returned = runner.find_ids(
        case.query,
        root,
        decisions=(tool == TOOL_FIND_DECISIONS),
        artifact_type=case.type,
    )
    return score_retrieval_case(returned, case)


# --- get_artifact --------------------------------------------------------------

# The stable resolve payload fields (ADR-007) a resolved lookup must carry.
RESOLVED_CONTRACT_FIELDS = ("schema_version", "id", "type", "title", "path")


def _path_matches(actual: str, expected_suffix: str) -> bool:
    """True when the returned path is the expected benchmark-relative file.

    The CLI echoes paths under the root it was given (absolute or relative),
    so cases pin the corpus-relative suffix rather than a machine-specific
    prefix.
    """
    actual_parts = PurePosixPath(Path(actual).as_posix()).parts
    expected_parts = PurePosixPath(expected_suffix).parts
    return actual_parts[-len(expected_parts):] == expected_parts


def run_get_artifact_case(
    runner: RacRunner, root: str, case: GetArtifactCase
) -> ConformanceResult:
    """One resolve-contract case: outcome, exit code, and payload fields."""
    result = runner.resolve(case.lookup, root)
    payload = result.payload()
    expect = case.expect
    checks: list[Check] = []

    outcome = str(expect["outcome"])
    if outcome == "resolved":
        checks.append(
            Check(
                "outcome",
                "error" not in payload,
                f"expected a resolved payload, got error={payload.get('error')!r}",
            )
        )
        missing = [f for f in RESOLVED_CONTRACT_FIELDS if f not in payload]
        checks.append(
            Check("contract_fields", not missing, f"missing fields: {missing}" if missing else "")
        )
    else:
        checks.append(
            Check(
                "outcome",
                payload.get("error") == outcome,
                f"expected error={outcome!r}, got {payload.get('error')!r}",
            )
        )

    expected_exit = int(expect.get("exit_code", 0 if outcome == "resolved" else 1))
    checks.append(
        Check(
            "exit_code",
            result.exit_code == expected_exit,
            f"expected exit {expected_exit}, got {result.exit_code}",
        )
    )

    for field_name in ("id", "type", "title"):
        if field_name in expect:
            checks.append(
                Check(
                    field_name,
                    payload.get(field_name) == expect[field_name],
                    f"expected {expect[field_name]!r}, got {payload.get(field_name)!r}",
                )
            )
    if "path" in expect:
        actual_path = str(payload.get("path", ""))
        checks.append(
            Check(
                "path",
                _path_matches(actual_path, str(expect["path"])),
                f"expected suffix {expect['path']!r}, got {actual_path!r}",
            )
        )
    if "paths" in expect:
        actual_paths = payload.get("paths", [])
        expected_paths = list(expect["paths"])
        matched = isinstance(actual_paths, list) and len(actual_paths) == len(
            expected_paths
        ) and all(
            any(_path_matches(str(actual), str(exp)) for actual in actual_paths)
            for exp in expected_paths
        )
        checks.append(
            Check("paths", matched, f"expected suffixes {expected_paths}, got {actual_paths}")
        )

    return ConformanceResult(
        case_id=case.id,
        category=case.category,
        checks=checks,
        context={"lookup": case.lookup, "returned_payload_error": payload.get("error")},
    )


# --- get_related ----------------------------------------------------------------


def _flatten_edges(relationships: dict[str, Any]) -> set[str]:
    """Every target id in an artifact's typed relationship map, casefolded."""
    edges: set[str] = set()
    for targets in relationships.values():
        if isinstance(targets, list):
            edges.update(str(target).casefold() for target in targets)
    return edges


def run_get_related_case(
    runner: RacRunner, root: str, case: GetRelatedCase
) -> ConformanceResult:
    """One relationship-edge case: incoming AND outgoing sets, exactly.

    The corpus-wide ``rac relationships --json`` map is read once; the case
    artifact's own entry is its outgoing edge set, and every other artifact
    whose targets name the case artifact contributes an incoming edge. Ids are
    compared case-insensitively; the sets must match the declaration exactly.
    """
    resolved = runner.resolve(case.artifact, root)
    if resolved.exit_code != 0:
        raise UsageError(
            f"get_related case {case.id!r}: artifact {case.artifact!r} did not resolve "
            f"in {root!r}"
        )
    artifact_path = str(resolved.payload()["path"])

    corpus_map = runner.relationships(root)
    id_by_path = runner.index_by_path(root)
    wanted = case.artifact.casefold()

    outgoing: set[str] = set()
    incoming: set[str] = set()
    for entry in corpus_map.get("artifacts", []):
        entry_path = str(entry.get("path", ""))
        entry_edges = _flatten_edges(entry.get("relationships", {}))
        if entry_path == artifact_path:
            outgoing = entry_edges
        elif wanted in entry_edges:
            source_id = id_by_path.get(entry_path)
            if source_id is None:
                raise UsageError(
                    f"get_related case {case.id!r}: no index id for source {entry_path!r}"
                )
            incoming.add(source_id.casefold())

    expected_incoming = {i.casefold() for i in case.expected_incoming}
    expected_outgoing = {o.casefold() for o in case.expected_outgoing}
    checks = [
        Check(
            "incoming_edges",
            incoming == expected_incoming,
            f"expected {sorted(expected_incoming)}, got {sorted(incoming)}",
        ),
        Check(
            "outgoing_edges",
            outgoing == expected_outgoing,
            f"expected {sorted(expected_outgoing)}, got {sorted(outgoing)}",
        ),
    ]
    negatives = {n.casefold() for n in case.must_not_return}
    violations = sorted(negatives & (incoming | outgoing))

    return ConformanceResult(
        case_id=case.id,
        category=case.category,
        checks=checks,
        violations=violations,
        context={
            "artifact": case.artifact,
            "returned_incoming": sorted(incoming),
            "returned_outgoing": sorted(outgoing),
        },
    )


# --- get_summary ----------------------------------------------------------------


def run_get_summary_case(
    runner: RacRunner, root: str, benchmark_dir: Path, case: GetSummaryCase
) -> ConformanceResult:
    """One portfolio-contract case: counts, empty shape, or byte stability."""
    case_root = str(benchmark_dir / case.root) if case.root else root
    result = runner.portfolio(case_root)
    checks: list[Check] = [
        Check("exit_code", result.exit_code == 0, f"exit {result.exit_code}")
    ]
    payload = result.payload()
    artifacts = payload.get("artifacts", {})

    if case.check == "counts":
        checks.append(
            Check("not_empty", payload.get("empty") is False, f"empty={payload.get('empty')!r}")
        )
        if "total" in case.expect:
            checks.append(
                Check(
                    "total",
                    artifacts.get("total") == case.expect["total"],
                    f"expected {case.expect['total']}, got {artifacts.get('total')}",
                )
            )
        for type_name, count in sorted(case.expect.get("by_type", {}).items()):
            checks.append(
                Check(
                    f"by_type.{type_name}",
                    artifacts.get("by_type", {}).get(type_name) == count,
                    f"expected {count}, got {artifacts.get('by_type', {}).get(type_name)}",
                )
            )
    elif case.check == "empty":
        checks.append(
            Check("empty", payload.get("empty") is True, f"empty={payload.get('empty')!r}")
        )
        checks.append(
            Check("total", artifacts.get("total") == 0, f"got {artifacts.get('total')}")
        )
    elif case.check == "byte_stable":
        rerun = runner.portfolio(case_root)
        checks.append(
            Check(
                "byte_stable",
                result.stdout == rerun.stdout,
                "two runs emitted different payload bytes",
            )
        )

    return ConformanceResult(
        case_id=case.id,
        category=case.category,
        checks=checks,
        context={"check": case.check},
    )
