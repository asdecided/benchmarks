# SPDX-License-Identifier: Apache-2.0
"""Answering-model seam for the GitChameleon evidence run.

Mirrors decisiongrounding's ``make_answering_model`` factory shape, minus the
structured-output scaffold: GitChameleon answers are code completions the
upstream harness extracts and executes, so the adapters return raw text.

Backends:

- ``offline-stub`` — a deterministic placeholder completion, for exercising the
  pipeline plumbing offline. Its output is clearly labelled and will fail the
  upstream tests; it is never a result.
- ``claude`` — the pinned Anthropic model (the same pin as decisiongrounding).
  Refuses without ``ANTHROPIC_API_KEY``.
- ``litellm:<alias>`` — any OpenAI-compatible gateway (ADR-0005 pattern).
  Refuses without ``LITELLM_BASE_URL``/``LITELLM_API_KEY`` (or the ``OPENAI_*``
  fallbacks).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request

# The held-constant instruction every arm shares; the task prompt itself is
# built by arms.task_prompt and never restates the pinned version.
SYSTEM = (
    "You are completing Python code for an existing codebase. Respect any "
    "engineering decisions supplied as context. Return only the completed code."
)

PINNED_CLAUDE = "claude-opus-4-8"
MAX_TOKENS = 2048
MAX_ATTEMPTS = 5


def _compose_user_prompt(prompt: str, grounding: list[str]) -> str:
    """One equal shot at the context window (the symmetric-injection rule):
    grounding first, then the task, for every arm alike."""
    if not grounding:
        return prompt
    blocks = "\n\n---\n\n".join(grounding)
    return f"Context — recorded engineering decisions:\n\n{blocks}\n\n---\n\n{prompt}"


class OfflineStubModel:
    """Deterministic plumbing-only completion. Never a result."""

    name = "offline-stub"
    version = "offline-stub"

    def __init__(self, seed: int = 0):
        self.seed = seed

    def complete(self, prompt: str, grounding: list[str]) -> str:
        return (
            f"# offline-stub deterministic placeholder (seed={self.seed}, "
            f"grounding_artifacts={len(grounding)})\n"
            "# Plumbing check only: this is not a model completion and will "
            "fail the upstream tests.\n"
            "pass\n"
        )


class ClaudeModel:
    name = "claude"
    version = PINNED_CLAUDE

    def __init__(self, seed: int = 0):
        self.seed = (
            seed  # recorded for provenance; the pinned model rejects sampling seeds
        )
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise SystemExit("the claude answering model needs ANTHROPIC_API_KEY")
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def complete(self, prompt: str, grounding: list[str]) -> str:
        import anthropic

        retryable = (
            anthropic.RateLimitError,
            anthropic.APIConnectionError,
            anthropic.InternalServerError,
        )
        for attempt in range(MAX_ATTEMPTS):
            try:
                msg = self._ensure_client().messages.create(
                    model=self.version,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM,
                    messages=[
                        {
                            "role": "user",
                            "content": _compose_user_prompt(prompt, grounding),
                        }
                    ],
                )
                return "".join(
                    block.text
                    for block in msg.content
                    if getattr(block, "type", "") == "text"
                )
            except retryable:
                if attempt + 1 == MAX_ATTEMPTS:
                    raise
                time.sleep(min(2**attempt, 30))
        raise AssertionError("unreachable")


class LiteLLMModel:
    """OpenAI-compatible chat-completions gateway (stdlib HTTP, no SDK)."""

    def __init__(self, alias: str, seed: int = 0):
        self.name = f"litellm:{alias}"
        self.version = alias
        self.seed = seed
        base = os.environ.get("LITELLM_BASE_URL") or os.environ.get("OPENAI_BASE_URL")
        key = os.environ.get("LITELLM_API_KEY") or os.environ.get("OPENAI_API_KEY")
        if not base or not key:
            raise SystemExit(
                "the litellm answering model needs LITELLM_BASE_URL and "
                "LITELLM_API_KEY (or the OPENAI_* fallbacks)"
            )
        self._base, self._key = base.rstrip("/"), key

    def complete(self, prompt: str, grounding: list[str]) -> str:
        body = json.dumps(
            {
                "model": self.version,
                "max_tokens": MAX_TOKENS,
                "messages": [
                    {"role": "system", "content": SYSTEM},
                    {
                        "role": "user",
                        "content": _compose_user_prompt(prompt, grounding),
                    },
                ],
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            f"{self._base}/chat/completions",
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._key}",
            },
        )
        for attempt in range(MAX_ATTEMPTS):
            try:
                with urllib.request.urlopen(req, timeout=300) as resp:
                    payload = json.loads(resp.read().decode("utf-8"))
                return payload["choices"][0]["message"]["content"]
            except urllib.error.HTTPError as exc:
                retryable = exc.code == 429 or 500 <= exc.code < 600
                if not retryable or attempt + 1 == MAX_ATTEMPTS:
                    raise
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(2**attempt, 30)
                time.sleep(delay)
            except urllib.error.URLError:
                if attempt + 1 == MAX_ATTEMPTS:
                    raise
                time.sleep(min(2**attempt, 30))
        raise AssertionError("unreachable")


def make_answering_model(name: str, seed: int = 0):
    if name == "offline-stub":
        return OfflineStubModel(seed)
    if name == "claude":
        return ClaudeModel(seed)
    if name.startswith("litellm:"):
        return LiteLLMModel(name.split(":", 1)[1], seed)
    raise SystemExit(
        f"unknown answering model {name!r}; expected offline-stub, claude, "
        "or litellm:<alias>"
    )
