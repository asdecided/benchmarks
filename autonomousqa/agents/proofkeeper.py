"""The reference agent: Proofkeeper, consumed over its published npm CLI.

The adapter shells out to the pinned `@itsthelore/proofkeeper` package inside
the node workspace — `node <workspace>/node_modules/@itsthelore/proofkeeper/dist/cli.js`
(the package's published bin entry, invoked by real path so the run cannot
silently no-op through a bin shim) — with the documented flags and BYOK
environment. It never imports Proofkeeper internals.

Exit codes are Proofkeeper's stable contract (0 verified, 1 not verified,
2 usage error). The human summary lines (`Drive:`, `Fidelity:`) are treated
as evidence and parsed defensively: exit 0 with no fidelity evidence is an
error, never a verification.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from agents.base import AgentAdapter, AgentInvocation, AgentOutcome, RunSpec

PACKAGE = "@itsthelore/proofkeeper"
CLI_RELPATH = Path("node_modules") / PACKAGE / "dist" / "cli.js"

# The two evidence lines `proofkeeper qa` prints. The dash between "green"
# and the stability verdict is an em dash in the published CLI; accept any
# dash so a font or locale change cannot flip scoring.
_FIDELITY = re.compile(
    r"^Fidelity: (\d+)/(\d+) re-runs green [—–-]+ (stable|unstable.*)$", re.MULTILINE
)
_DRIVE = re.compile(r"^Drive: (\d+) step\(s\), (.+)$", re.MULTILINE)
_COMPILED = re.compile(r"^Compiled: (.+)$", re.MULTILINE)


class ProofkeeperAdapter(AgentAdapter):
    name = "proofkeeper"

    def cli_path(self, workspace: Path) -> Path:
        cli = workspace / CLI_RELPATH
        if not cli.is_file():
            raise FileNotFoundError(
                f"{PACKAGE} is not installed in {workspace} — run `npm ci` there first"
            )
        return cli

    def version(self, workspace: Path) -> str:
        manifest = workspace / "node_modules" / PACKAGE / "package.json"
        return json.loads(manifest.read_text())["version"]

    def build(self, spec: RunSpec) -> AgentInvocation:
        argv = [
            "node",
            str(self.cli_path(spec.workspace)),
            "qa",
            "--graph-file", str(spec.graph_file),
            "--url", spec.start_url,
            "--capability", spec.capability_id,
            "--n", str(spec.n),
            # --base-url is left to its documented default (--url) so the
            # compiled test replays from the same start URL that was driven.
            "--out-dir", str(spec.out_dir),
        ]
        if spec.max_steps is not None:
            argv += ["--max-steps", str(spec.max_steps)]
        if spec.extension_dir is not None:
            argv += ["--extension", str(spec.extension_dir)]
        env = dict(spec.extra_env)
        if spec.proxy_base_url is not None:
            # Route the drive's model traffic through the harness proxy: the
            # published BYOK seam (OPENAI_BASE_URL) is how tokens get metered
            # without touching agent internals.
            env["OPENAI_BASE_URL"] = spec.proxy_base_url
            env.setdefault("OPENAI_API_KEY", "metered-by-harness")
        if spec.model is not None:
            env["OPENAI_MODEL"] = spec.model
        return AgentInvocation(argv=argv, env=env, cwd=spec.workspace)

    def parse(self, stdout: str, exit_code: int) -> AgentOutcome:
        fidelity = _FIDELITY.search(stdout)
        drive = _DRIVE.search(stdout)
        compiled = _COMPILED.search(stdout)
        passed = int(fidelity.group(1)) if fidelity else None
        attempts = int(fidelity.group(2)) if fidelity else None
        stable = fidelity.group(3) == "stable" if fidelity else None
        steps = int(drive.group(1)) if drive else None
        finished = drive.group(2) == "finished" if drive else None
        if exit_code == 0 and fidelity is None:
            return AgentOutcome(
                exit_code=exit_code,
                verified=False,
                drive_steps=steps,
                drive_finished=finished,
                spec_path=compiled.group(1) if compiled else None,
                error="exit 0 without fidelity evidence in output; not counted as verified",
            )
        return AgentOutcome(
            exit_code=exit_code,
            verified=exit_code == 0 and bool(stable),
            fidelity_passed=passed,
            fidelity_attempts=attempts,
            fidelity_stable=stable,
            drive_steps=steps,
            drive_finished=finished,
            spec_path=compiled.group(1) if compiled else None,
        )
