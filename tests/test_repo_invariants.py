# SPDX-License-Identifier: Apache-2.0
"""Repository-wide invariants: no engine coupling, CI never rebaselines."""

from __future__ import annotations

import re

from conftest import BENCHMARKS, REPO_ROOT

# The engine boundary (DG-ADR-0001): rac is an external CLI on PATH, never an
# import. Matches `import rac`, `from rac import ...`, `import rac.x`.
_ENGINE_IMPORT = re.compile(r"^\s*(?:import\s+rac\b|from\s+rac\b)", re.MULTILINE)


# Non-gated evidence-run subdirs are inside the engine boundary too.
EVIDENCE_DIRS = ("gitchameleon", "scale", "granularity")


def _suite_python_files():
    yield from (REPO_ROOT / "harness").rglob("*.py")
    yield from (REPO_ROOT / "tests").rglob("*.py")
    for bench in BENCHMARKS + EVIDENCE_DIRS:
        yield from (REPO_ROOT / bench).rglob("*.py")


def test_no_engine_coupling():
    offenders = [
        path.relative_to(REPO_ROOT)
        for path in _suite_python_files()
        if _ENGINE_IMPORT.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"engine imports found (DG-ADR-0001 forbids them): {offenders}"


def test_ci_workflows_never_rebaseline():
    """No CI step may run ``--update-baseline``: re-baselining is human-gated.
    Checks executed ``run:`` commands, not comment prose, so a workflow may
    still explain the rule it enforces."""
    import yaml

    workflows = REPO_ROOT / ".github" / "workflows"
    checked = 0
    for wf in sorted(workflows.glob("*.yml")):
        data = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
        for job in (data.get("jobs") or {}).values():
            for step in job.get("steps", []) or []:
                checked += 1
                assert "--update-baseline" not in (step.get("run") or ""), wf.name
    assert checked > 0, "no CI steps found — the workflow file is missing"


def test_every_benchmark_ships_its_committed_inputs():
    for bench in BENCHMARKS:
        root = REPO_ROOT / bench
        for required in ("run.py", "queries.json", "baseline.json", "config.json",
                         "README.md"):
            assert (root / required).is_file(), f"{bench}/{required} missing"
        assert (root / "corpus").is_dir(), f"{bench}/corpus missing"
        assert (root / "decisions").is_dir(), f"{bench}/decisions missing"
