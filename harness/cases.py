# SPDX-License-Identifier: Apache-2.0
"""Committed inputs: benchmark config, query set, baseline.

Each benchmark subdir commits four inputs — ``corpus/``, ``queries.json``,
``baseline.json``, ``config.json`` — and this module loads and validates the
JSON three. A malformed input is a :class:`UsageError` (exit 2), never a
silently skipped case.

The config's ``tool`` names the Lore MCP tool the benchmark scores and picks
the case shape:

- ``search_artifacts`` / ``find_decisions`` — ranked retrieval cases
  (``kind == "retrieval"``): P@k / R@k / MRR over the returned list, with a
  full-returned-list hard-negative window.
- ``get_artifact`` / ``get_related`` / ``get_summary`` — contract cases
  (``kind == "conformance"``): deterministic pass/fail checks, gated at 1.0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.errors import UsageError

TOOL_SEARCH = "search_artifacts"
TOOL_FIND_DECISIONS = "find_decisions"
TOOL_GET_ARTIFACT = "get_artifact"
TOOL_GET_RELATED = "get_related"
TOOL_GET_SUMMARY = "get_summary"

RETRIEVAL_TOOLS = (TOOL_SEARCH, TOOL_FIND_DECISIONS)
CONFORMANCE_TOOLS = (TOOL_GET_ARTIFACT, TOOL_GET_RELATED, TOOL_GET_SUMMARY)

KIND_RETRIEVAL = "retrieval"
KIND_CONFORMANCE = "conformance"

# The ranks retrieval benchmarks report Precision@k / Recall@k at (ADR-066
# family form; same ranks as rac eval).
K_VALUES: tuple[int, ...] = (1, 3, 5)

RESOLVE_OUTCOMES = ("resolved", "not-found", "duplicate")
SUMMARY_CHECKS = ("counts", "empty", "byte_stable")


@dataclass(frozen=True)
class BenchmarkConfig:
    """The committed gate config: which tool, floors, and tolerance."""

    tool: str
    tolerance: float
    floors: dict[str, Any]

    @property
    def kind(self) -> str:
        return KIND_RETRIEVAL if self.tool in RETRIEVAL_TOOLS else KIND_CONFORMANCE


@dataclass(frozen=True)
class RetrievalCase:
    """One ranked-retrieval case: query in, ordered id list scored.

    ``relevant`` has at least one id by construction; ``must_not_return`` is
    the hard-negative set, judged against the FULL returned list (the top-5
    window under-enforced the "never surface a superseded decision" claim).
    ``type`` is the optional ``--type`` filter for ``search_artifacts`` cases.
    """

    id: str
    query: str
    category: str
    relevant: tuple[str, ...]
    must_not_return: tuple[str, ...] = ()
    type: str | None = None


@dataclass(frozen=True)
class GetArtifactCase:
    """One ``get_artifact`` contract case: a lookup and its expected outcome.

    ``expect`` pins the outcome (``resolved`` / ``not-found`` / ``duplicate``),
    the exit code, and any payload fields the case asserts (``id``, ``type``,
    ``title``, ``path``, ``paths``). Paths are benchmark-root-relative.
    """

    id: str
    category: str
    lookup: str
    expect: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class GetRelatedCase:
    """One relationship-edge case: expected incoming AND outgoing id sets.

    The outgoing direction is the previously unguarded one. ``must_not_return``
    ids must not appear in either returned edge set.
    """

    id: str
    category: str
    artifact: str
    expected_incoming: tuple[str, ...] = ()
    expected_outgoing: tuple[str, ...] = ()
    must_not_return: tuple[str, ...] = ()


@dataclass(frozen=True)
class GetSummaryCase:
    """One ``get_summary`` contract case against ``rac portfolio --json``.

    ``check`` is one of ``counts`` (artifact totals match the fixture
    composition), ``empty`` (the empty-corpus shape), or ``byte_stable``
    (two runs emit byte-identical payloads). ``root`` optionally points the
    case at a sibling fixture directory (e.g. the empty corpus), relative to
    the benchmark directory.
    """

    id: str
    category: str
    check: str
    root: str | None = None
    expect: dict[str, Any] = field(default_factory=dict)


def _load_json(path: str, what: str) -> Any:
    p = Path(path)
    if not p.is_file():
        raise UsageError(f"{what} not found: {path}")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise UsageError(f"cannot read {what}: {path}: {exc}") from None
    except json.JSONDecodeError as exc:
        raise UsageError(f"malformed {what}: {path}: {exc}") from None


def load_config(path: str) -> BenchmarkConfig:
    """Load the committed benchmark config — tool, floors, tolerance."""
    data = _load_json(path, "config")
    if not isinstance(data, dict):
        raise UsageError(f"malformed config: {path}: expected an object")
    tool = data.get("tool")
    if tool not in RETRIEVAL_TOOLS + CONFORMANCE_TOOLS:
        raise UsageError(
            f"malformed config: {path}: 'tool' must be one of "
            f"{RETRIEVAL_TOOLS + CONFORMANCE_TOOLS}"
        )
    if "floors" not in data or "tolerance" not in data:
        raise UsageError(f"malformed config: {path}: expected 'floors' and 'tolerance'")
    return BenchmarkConfig(
        tool=str(tool), tolerance=float(data["tolerance"]), floors=data["floors"]
    )


def load_baseline(path: str) -> dict[str, Any]:
    """Load the committed baseline ``metrics`` object."""
    data = _load_json(path, "baseline")
    if not isinstance(data, dict) or "overall" not in data:
        raise UsageError(f"malformed baseline: {path}: expected a metrics object")
    return data


def load_query_set(path: str, tool: str) -> list[Any]:
    """Parse the committed query set for ``tool``, validating each case."""
    data = _load_json(path, "query set")
    cases_raw = data.get("cases") if isinstance(data, dict) else data
    if not isinstance(cases_raw, list) or not cases_raw:
        raise UsageError(f"malformed query set: {path}: expected a non-empty 'cases' list")
    parser = _CASE_PARSERS[tool]
    cases: list[Any] = []
    seen_ids: set[str] = set()
    for i, raw in enumerate(cases_raw):
        if not isinstance(raw, dict):
            raise UsageError(f"malformed query set: {path}: case {i} is not an object")
        case = parser(raw, path, i)
        if case.id in seen_ids:
            raise UsageError(f"malformed query set: {path}: duplicate case id {case.id!r}")
        seen_ids.add(case.id)
        cases.append(case)
    return cases


def _require(raw: dict, field_name: str, path: str, index: int) -> Any:
    if field_name not in raw:
        raise UsageError(f"malformed query set: {path}: case {index} missing {field_name!r}")
    return raw[field_name]


def _str_tuple(value: Any, field_name: str, case_id: str, path: str) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise UsageError(
            f"malformed query set: {path}: case {case_id!r} {field_name!r} must be a list"
        )
    return tuple(str(v) for v in value)


def _parse_retrieval(raw: dict, path: str, index: int) -> RetrievalCase:
    case_id = str(_require(raw, "id", path, index))
    relevant = _require(raw, "relevant", path, index)
    if not isinstance(relevant, list) or not relevant:
        raise UsageError(
            f"malformed query set: {path}: case {case_id!r} 'relevant' must be a "
            "non-empty list"
        )
    artifact_type = raw.get("type")
    if artifact_type is not None and not isinstance(artifact_type, str):
        raise UsageError(f"malformed query set: {path}: case {case_id!r} 'type' must be a string")
    return RetrievalCase(
        id=case_id,
        query=str(_require(raw, "query", path, index)),
        category=str(_require(raw, "category", path, index)),
        relevant=tuple(str(r) for r in relevant),
        must_not_return=_str_tuple(raw.get("must_not_return", []), "must_not_return", case_id, path),
        type=artifact_type,
    )


def _parse_get_artifact(raw: dict, path: str, index: int) -> GetArtifactCase:
    case_id = str(_require(raw, "id", path, index))
    expect = _require(raw, "expect", path, index)
    if not isinstance(expect, dict) or expect.get("outcome") not in RESOLVE_OUTCOMES:
        raise UsageError(
            f"malformed query set: {path}: case {case_id!r} 'expect.outcome' must be "
            f"one of {RESOLVE_OUTCOMES}"
        )
    return GetArtifactCase(
        id=case_id,
        category=str(_require(raw, "category", path, index)),
        lookup=str(_require(raw, "lookup", path, index)),
        expect=expect,
    )


def _parse_get_related(raw: dict, path: str, index: int) -> GetRelatedCase:
    case_id = str(_require(raw, "id", path, index))
    case = GetRelatedCase(
        id=case_id,
        category=str(_require(raw, "category", path, index)),
        artifact=str(_require(raw, "artifact", path, index)),
        expected_incoming=_str_tuple(
            _require(raw, "expected_incoming", path, index), "expected_incoming", case_id, path
        ),
        expected_outgoing=_str_tuple(
            _require(raw, "expected_outgoing", path, index), "expected_outgoing", case_id, path
        ),
        must_not_return=_str_tuple(
            raw.get("must_not_return", []), "must_not_return", case_id, path
        ),
    )
    return case


def _parse_get_summary(raw: dict, path: str, index: int) -> GetSummaryCase:
    case_id = str(_require(raw, "id", path, index))
    check = _require(raw, "check", path, index)
    if check not in SUMMARY_CHECKS:
        raise UsageError(
            f"malformed query set: {path}: case {case_id!r} 'check' must be one of "
            f"{SUMMARY_CHECKS}"
        )
    root = raw.get("root")
    if root is not None and not isinstance(root, str):
        raise UsageError(f"malformed query set: {path}: case {case_id!r} 'root' must be a string")
    expect = raw.get("expect", {})
    if not isinstance(expect, dict):
        raise UsageError(
            f"malformed query set: {path}: case {case_id!r} 'expect' must be an object"
        )
    return GetSummaryCase(
        id=case_id,
        category=str(_require(raw, "category", path, index)),
        check=str(check),
        root=root,
        expect=expect,
    )


_CASE_PARSERS = {
    TOOL_SEARCH: _parse_retrieval,
    TOOL_FIND_DECISIONS: _parse_retrieval,
    TOOL_GET_ARTIFACT: _parse_get_artifact,
    TOOL_GET_RELATED: _parse_get_related,
    TOOL_GET_SUMMARY: _parse_get_summary,
}
