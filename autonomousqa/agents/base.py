"""Adapter contract between the harness and any autonomous-QA agent.

An adapter builds the agent's CLI invocation from a RunSpec and parses the
agent's raw evidence (stdout + exit code) into a typed outcome. Parsing is a
pure function so recorded runs re-score deterministically, without re-running
the agent or re-spending tokens.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class RunSpec:
    """Everything an adapter needs to drive one capability of one app."""

    app_name: str
    modality: str
    capability_id: str
    graph_file: Path
    start_url: str
    base_url: str
    workspace: Path
    out_dir: Path
    n: int = 3
    max_steps: int | None = None
    extension_dir: Path | None = None
    proxy_base_url: str | None = None
    model: str | None = None
    extra_env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AgentInvocation:
    """A concrete subprocess the harness will run and time."""

    argv: list[str]
    env: dict[str, str]
    cwd: Path


@dataclass(frozen=True)
class AgentOutcome:
    """The typed verdict parsed from an agent run's raw evidence.

    `verified` is deliberately strict: a bare exit code 0 with no fidelity
    evidence in the output parses as an error, never as verified.
    """

    exit_code: int
    verified: bool
    fidelity_passed: int | None = None
    fidelity_attempts: int | None = None
    fidelity_stable: bool | None = None
    drive_steps: int | None = None
    drive_finished: bool | None = None
    spec_path: str | None = None
    error: str | None = None

    def as_dict(self) -> dict:
        return {
            "exit_code": self.exit_code,
            "verified": self.verified,
            "fidelity": {
                "passed": self.fidelity_passed,
                "attempts": self.fidelity_attempts,
                "stable": self.fidelity_stable,
            },
            "drive": {"steps": self.drive_steps, "finished": self.drive_finished},
            "spec_path": self.spec_path,
            "error": self.error,
        }


class AgentAdapter(ABC):
    """One autonomous-QA agent, consumed strictly over its published CLI."""

    name: str = "abstract"

    @abstractmethod
    def version(self, workspace: Path) -> str:
        """The agent's pinned version inside the given workspace."""

    @abstractmethod
    def build(self, spec: RunSpec) -> AgentInvocation:
        """Build the CLI invocation for one capability run."""

    @abstractmethod
    def parse(self, stdout: str, exit_code: int) -> AgentOutcome:
        """Parse raw run evidence into an outcome. Pure and deterministic."""
