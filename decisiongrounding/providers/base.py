"""Uniform provider-adapter contract shared by every benchmark arm.

Each arm is a `Provider`. It gets exactly one symmetric opportunity to
populate the answering model's context (`prepare`), then answers the task
(`respond`). Arms differ ONLY in how they select and assemble grounding from
the corpus; the answering model and the prompt scaffold are held constant.

This isolates *retrieval/assembly quality*. It does NOT test whether a
pull-based MCP actually gets consulted in production — that is a separate
deployment question (see README, "Symmetric injection caveat").
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:  # avoid an import cycle with answering.py
    from .answering import AnsweringModel


# The held-constant prompt scaffold. Every arm feeds its grounding into this
# identical frame, so any difference in outcome is attributable to grounding
# assembly, not to prompt phrasing.
SCAFFOLD = (
    "You are a senior engineer about to act on a task. Prior team decisions "
    "may bind your action. Using ONLY the grounding provided, decide whether "
    "the proposed action is permitted or prohibited, follow any superseding "
    "decision over the decision it supersedes, do not invent constraints that "
    "the grounding does not state, and cite the decision id(s) you relied on."
)


@dataclass(frozen=True)
class CorpusArtifact:
    """One markdown artifact in a scenario's project corpus."""

    id: str
    type: str
    path: str
    text: str
    supersedes: tuple[str, ...] = ()
    filler: bool = False


@dataclass(frozen=True)
class Task:
    """What the agent is asked to do, and the action it is on the verge of."""

    prompt: str
    proposed_action: str


@dataclass(frozen=True)
class GroundingContext:
    """What an arm placed in the answering model's context this run."""

    text: str
    artifacts_supplied: tuple[str, ...]
    token_estimate: int


@dataclass(frozen=True)
class Action:
    """A concrete step in a proposed change."""

    kind: str
    target: str
    detail: str


@dataclass
class ProposedChange:
    """The answering model's structured proposal, scored deterministically."""

    summary: str
    actions: list[Action] = field(default_factory=list)
    cites_decisions: list[str] = field(default_factory=list)
    asserts_prohibition: bool = False
    asserts_permission: bool = False


def estimate_tokens(text: str) -> int:
    """Cheap, deterministic token estimate (~4 chars/token)."""
    return (len(text) + 3) // 4


class ContextWindowExceededError(RuntimeError):
    """The assembled prompt (scaffold + grounding + task) would not fit the
    answering model's context window, even before an output-token reserve.

    Raised BEFORE the answering model is called (see `check_context_window`),
    so it costs nothing and is distinguishable from a transport/schema error —
    the runner records it as its own outcome rather than folding it into
    generic `errors`, so an arm that structurally cannot fit a large corpus
    (typically `context_dump` at high N) is not misread as one that fit the
    corpus and then answered wrong. `token_estimate` carries the prompt size
    that tripped the check, for cost-curve bookkeeping on a cell that never
    made an API call.
    """

    def __init__(self, message: str, token_estimate: int = 0) -> None:
        super().__init__(message)
        self.token_estimate = token_estimate


# Headroom reserved for the answering model's response (max_tokens=2048 across
# every real backend, see providers/answering.py) plus a small safety margin —
# subtracted from the context window before comparing against the prompt.
RESPONSE_RESERVE_TOKENS = 4096


def context_window_needed(grounding: GroundingContext, task: Task) -> int:
    """Estimated total prompt size: the held-constant scaffold + this arm's
    grounding + the task text — the same three pieces every real backend
    renders into one prompt (see `answering._task_user_prompt`)."""
    return (
        estimate_tokens(SCAFFOLD)
        + grounding.token_estimate
        + estimate_tokens(task.prompt)
        + estimate_tokens(task.proposed_action)
    )


def check_context_window(grounding: GroundingContext, task: Task, answering_model) -> None:
    """Raise `ContextWindowExceededError` when this grounding would not fit the
    answering model's context window, reserving headroom for its response.

    Every arm's `respond()` calls this identically (see `Provider.respond`),
    so hitting the ceiling is an arm-symmetric, first-class outcome rather
    than something one arm discovers via a raw API error and another doesn't.
    `answering_model.context_window_tokens` is `None` for backends with no
    known/enforced limit (the offline stub, an unpinned gateway alias), in
    which case this is a no-op and the real API call is the only check.
    """
    limit = getattr(answering_model, "context_window_tokens", None)
    if limit is None:
        return
    needed = context_window_needed(grounding, task)
    if needed + RESPONSE_RESERVE_TOKENS > limit:
        raise ContextWindowExceededError(
            f"prompt (~{needed} tokens, including {grounding.token_estimate} of "
            f"grounding) plus a {RESPONSE_RESERVE_TOKENS}-token response reserve "
            f"exceeds the answering model's {limit}-token context window",
            token_estimate=needed,
        )


class Provider(ABC):
    """Base arm. Subclasses implement `prepare`; `respond` is shared."""

    #: Stable arm name, matches the run_result.schema.json `arm` enum.
    name: str = "base"

    def __init__(self, answering_model: "AnsweringModel") -> None:
        self.answering_model = answering_model
        self._grounding: GroundingContext | None = None

    @abstractmethod
    def prepare(self, corpus: list[CorpusArtifact]) -> None:
        """Assemble this arm's grounding from the corpus (called once)."""

    def assemble(self, task: Task) -> GroundingContext:
        """Return this arm's grounding for the task, WITHOUT calling the answering
        model. Base arms fix their grounding in prepare(); task-dependent arms
        (naive_rag, rac) override this. Splitting assembly from answering lets the
        runner build every prompt first and batch the answering calls."""
        if self._grounding is None:
            raise RuntimeError(f"{self.name}: prepare() must run before assemble()")
        return self._grounding

    def respond(self, task: Task) -> ProposedChange:
        """Answer the task using the held-constant scaffold + answering model.

        Checks the context window BEFORE calling the answering model (see
        `check_context_window`) so a grounding that cannot fit is a first-class
        `ContextWindowExceededError`, not a raw transport failure.
        """
        grounding = self.assemble(task)
        check_context_window(grounding, task, self.answering_model)
        return self.answering_model.respond(SCAFFOLD, grounding, task)

    @property
    def grounding(self) -> GroundingContext:
        if self._grounding is None:
            raise RuntimeError(f"{self.name}: prepare() has not run")
        return self._grounding
