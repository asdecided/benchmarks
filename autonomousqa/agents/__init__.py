"""The agent seam: adapters that turn a RunSpec into a CLI invocation.

The benchmark is agent-agnostic — a property of the frozen apps, the seeded
corpora, and the deterministic scorer. Every agent is invoked through an
AgentAdapter; adding a second agent means adding one adapter here, nothing
else changes.
"""
from agents.base import AgentAdapter, AgentInvocation, AgentOutcome, RunSpec
from agents.proofkeeper import ProofkeeperAdapter

AGENTS: dict[str, AgentAdapter] = {
    ProofkeeperAdapter.name: ProofkeeperAdapter(),
}

__all__ = [
    "AGENTS",
    "AgentAdapter",
    "AgentInvocation",
    "AgentOutcome",
    "ProofkeeperAdapter",
    "RunSpec",
]
