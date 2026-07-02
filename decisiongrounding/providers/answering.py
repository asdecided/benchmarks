"""The held-constant answering model.

Every arm feeds its assembled grounding into the SAME answering model behind
the SAME scaffold. Arms differ only in the grounding; the answering model is a
fixed function of (scaffold, grounding, task).

Two implementations:

* `ScriptedAnsweringModel` — a deterministic, offline stand-in. It reads ONLY
  the grounding text and applies a transparent prose-reading policy: refrain
  when a relevant, non-superseded decision prohibits the action; otherwise
  proceed, folding in any stated constraint; follow a decision over one it
  visibly supersedes; never invent a constraint the grounding does not state.
  CRUCIALLY its behaviour depends only on what is *visible in the grounding*,
  never on the gold label — so the demo honestly exercises retrieval/assembly
  quality. Its output is a plumbing illustration, NOT a benchmark result.

* `ClaudeAnsweringModel` — the real, pinned answering model (stub). Renders one
  prompt, calls the API at temperature 0 with a fixed seed, parses a structured
  ProposedChange back. Filled in behind the `[real]` extra.
"""

from __future__ import annotations

import os
import re
from abc import ABC, abstractmethod

from .base import Action, GroundingContext, ProposedChange, Task
from .grounding_format import parse_blocks

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "to", "of", "and", "or", "for", "in", "on", "with", "without",
    "is", "are", "be", "as", "by", "this", "that", "it", "its", "our", "we", "you",
    "must", "not", "no", "do", "does", "should", "shall", "may", "can", "will",
    "all", "any", "from", "into", "at", "use", "using", "team", "service", "api",
}

# Prose signals an agent would read out of plain markdown. Arm-agnostic: the
# same extraction runs over whatever text is present in the grounding.
_PROHIBIT = re.compile(
    r"(must not|may not|shall not|do not|does not|cannot|never|prohibit|"
    r"forbidden|not permitted|not allowed|without (?:explicit )?authorization|"
    r"requires? (?:explicit )?authorization|requires? sign-?off)",
    re.IGNORECASE,
)
_CONSTRAINT = re.compile(
    r"\b(?:must|shall|are required to|is required to|always)\s+([^.\n]+)",
    re.IGNORECASE,
)
# A lone "Superseded" status line marks an artifact as retired. We deliberately
# do NOT treat the prose "superseded by ..." as self-marking, because a
# superseding decision routinely mentions that phrase about the decision it
# replaces — reading it as self-marking would retire the wrong artifact.
_SUPERSEDED_SELF = re.compile(r"^\s*superseded\s*$", re.IGNORECASE | re.MULTILINE)
_SUPERSEDES_OTHER = re.compile(r"supersedes\s+([A-Za-z0-9-]+)", re.IGNORECASE)


def _content_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN.findall(text.lower()) if t not in _STOP and len(t) > 2}


def usage_dict(usage) -> dict | None:
    """Normalise a Messages `usage` object (sync response or a Batch result's
    `.message.usage`) into a plain {input_tokens, output_tokens} dict, or None
    when the model reports no usage (the offline stub)."""
    if usage is None:
        return None
    inp = getattr(usage, "input_tokens", None)
    out = getattr(usage, "output_tokens", None)
    if inp is None and out is None:
        return None
    return {"input_tokens": int(inp or 0), "output_tokens": int(out or 0)}


class AnsweringModel(ABC):
    name: str = "base"
    version: str = "0"
    temperature: float | None = 0.0  # None when the pinned model exposes no knob
    seed: int = 0
    # Real token usage from the most recent respond(), so the runner can record
    # per-cell cost. None for the offline stub (it makes no API call).
    last_usage: dict | None = None

    @abstractmethod
    def respond(
        self, scaffold: str, grounding: GroundingContext, task: Task
    ) -> ProposedChange:
        ...


class ScriptedAnsweringModel(AnsweringModel):
    """Deterministic offline agent. Reads only the grounding; ignores gold."""

    name = "offline-stub"
    version = "scaffold-0"
    temperature = 0.0

    def __init__(self, seed: int = 0, relevance_threshold: int = 2) -> None:
        self.seed = seed
        self.relevance_threshold = relevance_threshold

    def respond(
        self, scaffold: str, grounding: GroundingContext, task: Task
    ) -> ProposedChange:
        blocks = parse_blocks(grounding.text)
        action_tokens = _content_tokens(task.proposed_action)

        # 1. Which artifact ids are *visibly* superseded in this grounding?
        superseded: set[str] = set()
        for artifact_id, _type, body in blocks:
            if _SUPERSEDED_SELF.search(body):
                superseded.add(artifact_id)
            for other in _SUPERSEDES_OTHER.findall(body):
                superseded.add(other)

        # 2. Relevant, non-superseded decisions the agent would act on.
        relevant_active: list[str] = []
        prohibiting: list[str] = []
        constraints: list[tuple[str, str]] = []  # (artifact_id, constraint_clause)
        for artifact_id, artifact_type, body in blocks:
            if artifact_type != "decision" or artifact_id in superseded:
                continue
            overlap = len(action_tokens & _content_tokens(body))
            if overlap < self.relevance_threshold:
                continue
            relevant_active.append(artifact_id)
            if _PROHIBIT.search(body):
                prohibiting.append(artifact_id)
            else:
                m = _CONSTRAINT.search(body)
                if m:
                    constraints.append((artifact_id, m.group(1).strip()))

        # 3. Decide. Refrain on a live prohibition; otherwise proceed.
        if prohibiting:
            return ProposedChange(
                summary=(
                    "A prior decision prohibits this action; escalate for "
                    "explicit authorization instead of proceeding."
                ),
                actions=[
                    Action(
                        kind="escalate",
                        target="authorization",
                        detail="Request explicit sign-off before taking the action.",
                    )
                ],
                cites_decisions=sorted(set(prohibiting)),
                asserts_prohibition=True,
                asserts_permission=False,
            )

        # Proceed. Cite every relevant, live decision the agent relied on
        # (permitting ones included) so a later stale-decision check can see
        # whether the agent leaned on a superseded rule.
        detail = f"Proceed with: {task.proposed_action}."
        cites = sorted(set(relevant_active))
        if constraints:
            detail += " Constraint(s): " + "; ".join(c for _, c in constraints) + "."
        return ProposedChange(
            summary="No live decision prohibits this action; proceed.",
            actions=[Action(kind="implement", target="proposed_action", detail=detail)],
            cites_decisions=cites,
            asserts_prohibition=False,
            asserts_permission=True,
        )


# JSON Schema the answering model must return — mirrors providers.base.ProposedChange.
_PROPOSED_CHANGE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "actions": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "kind": {"type": "string"},
                    "target": {"type": "string"},
                    "detail": {"type": "string"},
                },
                "required": ["kind", "target", "detail"],
            },
        },
        "cites_decisions": {"type": "array", "items": {"type": "string"}},
        "asserts_prohibition": {"type": "boolean"},
        "asserts_permission": {"type": "boolean"},
    },
    "required": [
        "summary",
        "actions",
        "cites_decisions",
        "asserts_prohibition",
        "asserts_permission",
    ],
}


def _task_user_prompt(grounding: GroundingContext, task: Task) -> str:
    """The single user-message text every REAL answering backend renders.

    Shared so transport adapters (Anthropic-native, OpenAI-compatible) cannot
    drift: the held-constant contract is (scaffold, this prompt, the
    ProposedChange schema); only the wire format may differ per backend.
    """
    return (
        f"GROUNDING (use only this):\n{grounding.text}\n\n"
        f"TASK: {task.prompt}\n"
        f"PROPOSED ACTION: {task.proposed_action}\n\n"
        "Return a ProposedChange. Set asserts_prohibition=true and refrain "
        "(no prohibited action in `actions`) if a governing decision forbids "
        "the action; set asserts_permission=true and proceed otherwise. Cite "
        "the decision id(s) you relied on. Do not invent constraints absent "
        "from the grounding."
    )


def _proposed_change_from_json_text(text: str, backend: str) -> ProposedChange:
    """Decode the structured-output JSON text into a ProposedChange.

    Shared by every real backend's parse path. Fails loudly on non-JSON or a
    missing field — a silent fallback would turn a transport problem into a
    scored answer, which the determinism rules forbid.
    """
    import json

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"{backend} returned non-JSON despite the structured-output schema: {exc}"
        ) from exc
    try:
        return ProposedChange(
            summary=data["summary"],
            actions=[
                Action(a["kind"], a["target"], a["detail"]) for a in data["actions"]
            ],
            cites_decisions=list(data["cites_decisions"]),
            asserts_prohibition=bool(data["asserts_prohibition"]),
            asserts_permission=bool(data["asserts_permission"]),
        )
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            f"{backend} JSON missing an expected ProposedChange field: {exc}"
        ) from exc


class ClaudeAnsweringModel(AnsweringModel):
    """Real pinned answering model (Claude Opus 4.8), wired behind `[real]`.

    Held identical across arms; only the grounding varies. Note: Opus 4.8
    rejects `temperature`/`top_p`/`seed` (400), so there is no temperature/seed
    knob to pin — determinism is approximated by the fixed model id + scaffold +
    structured JSON output, and run-to-run variance is reported as a metric.
    `temperature` is recorded as None and `seed` is bookkeeping only.
    """

    name = "claude"
    version = "claude-opus-4-8"  # pinned model id
    temperature = None

    def __init__(self, seed: int = 0, effort: str = "low") -> None:
        self.seed = seed
        self.effort = effort  # low keeps the constrained decision task cheap/stable
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            try:
                import anthropic  # type: ignore  # provided by the [real] extra
            except ImportError as exc:  # pragma: no cover - exercised only for real
                raise RuntimeError(
                    "the claude answering model needs the `anthropic` package: "
                    "pip install -e '.[real]'"
                ) from exc
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise RuntimeError(
                    "the claude answering model needs ANTHROPIC_API_KEY set in the "
                    "environment (export ANTHROPIC_API_KEY=...)."
                )
            self._client = anthropic.Anthropic()
        return self._client

    def build_request(
        self, scaffold: str, grounding: GroundingContext, task: Task
    ) -> dict:
        """The exact `messages.create` kwargs for this cell. Used directly by
        respond() and collected by the batch runner so the answering calls can be
        submitted together via the Batch API (50% of standard price). No
        temperature / seed: Opus 4.8 rejects them; effort is pinned and structured
        output forces the ProposedChange shape — identical across arms."""
        user = _task_user_prompt(grounding, task)
        return {
            "model": self.version,
            "max_tokens": 2048,
            "system": scaffold,
            "messages": [{"role": "user", "content": user}],
            "output_config": {
                "effort": self.effort,
                "format": {"type": "json_schema", "schema": _PROPOSED_CHANGE_SCHEMA},
            },
        }

    def parse_message(self, resp) -> ProposedChange:
        """Decode a Messages API response — synchronous or a Batch result's
        `.message` — into a ProposedChange."""
        if getattr(resp, "stop_reason", None) == "refusal":
            # Treat a safety refusal as a non-answer: assert nothing, cite nothing.
            return ProposedChange(summary="model refused", actions=[])
        text = next(
            (b.text for b in resp.content if getattr(b, "type", None) == "text"), None
        )
        if text is None:
            raise RuntimeError(
                f"claude returned no text block to parse (stop_reason="
                f"{getattr(resp, 'stop_reason', None)!r})."
            )
        return _proposed_change_from_json_text(text, "claude")

    def respond(
        self, scaffold: str, grounding: GroundingContext, task: Task
    ) -> ProposedChange:
        client = self._ensure_client()
        resp = client.messages.create(**self.build_request(scaffold, grounding, task))
        self.last_usage = usage_dict(getattr(resp, "usage", None))
        return self.parse_message(resp)


class OpenAICompatAnsweringModel(AnsweringModel):
    """Real answering model behind an OpenAI-compatible gateway (LiteLLM).

    Enterprise routing commonly exposes models only through LiteLLM's
    OpenAI-format `/chat/completions` surface with virtual keys, not
    Anthropic's native route. This adapter keeps the held-constant contract
    identical to :class:`ClaudeAnsweringModel` — same scaffold as the system
    message, same :func:`_task_user_prompt` user message, same
    ``_PROPOSED_CHANGE_SCHEMA`` — and changes ONLY the wire format:
    structured output is requested via OpenAI ``response_format`` /
    ``json_schema`` (which LiteLLM translates per backend) and parsed from
    ``choices[0].message.content``.

    Transport is stdlib ``urllib`` — the core spine stays dependency-free.
    Configuration: base URL from ``LITELLM_BASE_URL`` (fallback
    ``OPENAI_BASE_URL``), key from ``LITELLM_API_KEY`` (fallback
    ``OPENAI_API_KEY``). ``version`` records the full ``litellm:<alias>``
    spec string so a report is honest that a gateway alias, not a first-party
    pin, answered — pin the alias to a fixed model on the gateway, or the
    recorded identity is misleading. The Batch API is not part of the OpenAI
    surface: this backend is synchronous only.
    """

    name = "litellm"
    temperature = None

    def __init__(self, model: str, seed: int = 0, timeout: float = 300.0) -> None:
        if not model:
            raise ValueError("litellm answering model needs an alias: litellm:<model>")
        self.model = model
        self.version = f"litellm:{model}"
        self.seed = seed  # bookkeeping only, like the claude backend
        self.timeout = timeout

    @staticmethod
    def _base_url() -> str:
        base = os.environ.get("LITELLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
        if not base:
            raise RuntimeError(
                "the litellm answering model needs LITELLM_BASE_URL (or "
                "OPENAI_BASE_URL) pointing at the gateway's OpenAI-compatible root."
            )
        return base.rstrip("/")

    @staticmethod
    def _api_key() -> str:
        key = os.environ.get("LITELLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "the litellm answering model needs LITELLM_API_KEY (or "
                "OPENAI_API_KEY) set to the gateway's virtual key."
            )
        return key

    def build_request(
        self, scaffold: str, grounding: GroundingContext, task: Task
    ) -> dict:
        """The exact `/chat/completions` body for this cell.

        Same (scaffold, prompt, schema) triple as the Anthropic-native
        backend; ``strict`` asks the gateway to enforce the schema where the
        underlying provider supports it.
        """
        return {
            "model": self.model,
            "max_tokens": 2048,
            "messages": [
                {"role": "system", "content": scaffold},
                {"role": "user", "content": _task_user_prompt(grounding, task)},
            ],
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "proposed_change",
                    "strict": True,
                    "schema": _PROPOSED_CHANGE_SCHEMA,
                },
            },
        }

    def parse_response(self, payload: dict) -> ProposedChange:
        """Decode a `/chat/completions` JSON payload into a ProposedChange."""
        choices = payload.get("choices") or []
        if not choices:
            raise RuntimeError(f"litellm returned no choices: {payload!r}")
        choice = choices[0]
        if choice.get("finish_reason") == "content_filter":
            # The OpenAI-surface analogue of an Anthropic refusal stop.
            return ProposedChange(summary="model refused", actions=[])
        text = (choice.get("message") or {}).get("content")
        if not text:
            raise RuntimeError(
                f"litellm returned no message content "
                f"(finish_reason={choice.get('finish_reason')!r})."
            )
        return _proposed_change_from_json_text(text, "litellm")

    @staticmethod
    def parse_usage(payload: dict) -> dict | None:
        """Normalise OpenAI-shape usage into {input_tokens, output_tokens}."""
        usage = payload.get("usage")
        if not isinstance(usage, dict):
            return None
        inp = usage.get("prompt_tokens")
        out = usage.get("completion_tokens")
        if inp is None and out is None:
            return None
        return {"input_tokens": int(inp or 0), "output_tokens": int(out or 0)}

    def respond(
        self, scaffold: str, grounding: GroundingContext, task: Task
    ) -> ProposedChange:
        import json
        import urllib.error
        import urllib.request

        body = json.dumps(self.build_request(scaffold, grounding, task)).encode("utf-8")
        request = urllib.request.Request(
            f"{self._base_url()}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key()}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(
                f"litellm gateway returned HTTP {exc.code}: {detail}"
            ) from None
        self.last_usage = self.parse_usage(payload)
        return self.parse_response(payload)
