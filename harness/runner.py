# SPDX-License-Identifier: Apache-2.0
"""The subprocess seam: ``rac`` as an external CLI on ``PATH``.

Every retrieval the suite scores flows through this module, and nothing else
in the repository touches the engine — no ``import rac``, ever (DG-ADR-0001).
The scored surface is therefore exactly the published CLI contract: the same
``--json`` payloads and exit codes an agent integration consumes.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass

from harness.errors import UsageError


@dataclass(frozen=True)
class RacResult:
    """One finished ``rac`` invocation: exit code, streams, parsed payload."""

    argv: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str

    def payload(self) -> dict:
        """The stdout JSON object, or a :class:`UsageError` if unparsable."""
        try:
            data = json.loads(self.stdout)
        except json.JSONDecodeError as exc:
            raise UsageError(
                f"rac emitted non-JSON output for {' '.join(self.argv)}: {exc}"
            ) from None
        if not isinstance(data, dict):
            raise UsageError(f"rac emitted a non-object payload for {' '.join(self.argv)}")
        return data


class RacRunner:
    """Runs ``rac`` subcommands and hands back their JSON contracts."""

    def __init__(self, executable: str = "rac") -> None:
        if shutil.which(executable) is None:
            raise UsageError(
                f"'{executable}' not found on PATH — the suite consumes rac as an "
                "external CLI (DG-ADR-0001); install rac-core first"
            )
        self.executable = executable

    def run(self, *args: str) -> RacResult:
        argv = (self.executable, *args)
        try:
            completed = subprocess.run(argv, capture_output=True, text=True, check=False)
        except OSError as exc:
            raise UsageError(f"cannot execute {' '.join(argv)}: {exc}") from None
        return RacResult(
            argv=argv,
            exit_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def version(self) -> str:
        """The ``rac --version`` string, recorded in scorecard metadata."""
        result = self.run("--version")
        if result.exit_code != 0:
            raise UsageError(f"rac --version failed: {result.stderr.strip()}")
        return result.stdout.strip()

    # --- Retrieval surfaces (production order consumed verbatim) -------------

    def find_ids(
        self,
        query: str,
        root: str,
        *,
        decisions: bool = False,
        artifact_type: str | None = None,
    ) -> list[str]:
        """Returned ids for ``rac find`` in production rank order, unchanged.

        ``--decisions`` drives the live-decision filter (the ``find_decisions``
        MCP tool); ``--type`` drives the type filter. The two are mutually
        exclusive by the CLI contract.
        """
        args = ["find", query, root, "--json"]
        if decisions:
            args.append("--decisions")
        if artifact_type is not None:
            args.extend(["--type", artifact_type])
        result = self.run(*args)
        if result.exit_code != 0:
            raise UsageError(
                f"rac find failed (exit {result.exit_code}): {result.stderr.strip()}"
            )
        payload = result.payload()
        matches = payload.get("matches")
        if not isinstance(matches, list):
            raise UsageError("rac find payload has no 'matches' list")
        return [str(match["id"]) for match in matches]

    def resolve(self, artifact_id: str, root: str) -> RacResult:
        """The raw ``rac resolve`` outcome — conformance cases assert on it."""
        return self.run("resolve", artifact_id, root, "--json")

    def relationships(self, path: str) -> dict:
        """The ``rac relationships --json`` payload for a file or directory."""
        result = self.run("relationships", path, "--json")
        if result.exit_code != 0:
            raise UsageError(
                f"rac relationships failed (exit {result.exit_code}): {result.stderr.strip()}"
            )
        return result.payload()

    def portfolio(self, root: str) -> RacResult:
        """The raw ``rac portfolio`` outcome — conformance cases assert on it."""
        return self.run("portfolio", root, "--json")

    def index_by_path(self, root: str) -> dict[str, str]:
        """``{artifact path -> canonical id}`` from ``rac index --json``.

        Plumbing only: the map lets the harness name the *source* of an
        incoming relationship edge by id. It never re-orders or re-ranks
        anything the scored tool returned.
        """
        result = self.run("index", root, "--json")
        if result.exit_code != 0:
            raise UsageError(
                f"rac index failed (exit {result.exit_code}): {result.stderr.strip()}"
            )
        payload = result.payload()
        artifacts = payload.get("artifacts")
        if not isinstance(artifacts, list):
            raise UsageError("rac index payload has no 'artifacts' list")
        return {str(entry["path"]): str(entry["id"]) for entry in artifacts}
