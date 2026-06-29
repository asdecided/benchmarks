"""Probe a LiteLLM (or any) Anthropic endpoint for the three capabilities the
benchmark's answering model needs. Tiny spend (a couple of small calls).

    ANTHROPIC_BASE_URL=https://your-litellm/...   # the proxy base (Anthropic-native route)
    ANTHROPIC_API_KEY=sk-litellm-virtual-key      # the LiteLLM virtual key
    python -m scripts.litellm_probe                # or: --base-url ... --key ... --model ...

It reuses the EXACT request the benchmark sends (ClaudeAnsweringModel.build_request),
so a pass here means the real run will work through this endpoint.

Checks, in order:
  1. messages.create returns a text block that parses as the structured ProposedChange
     (this is what makes scoring deterministic), and reports token usage.
  2. messages.batches.create + retrieve work (the --batch / make real-batch path).
A failure on (2) only means: run the synchronous crossover through the proxy and
reserve --batch for a direct-Anthropic key.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from providers.answering import ClaudeAnsweringModel, usage_dict  # noqa: E402
from providers.base import SCAFFOLD, GroundingContext, Task  # noqa: E402


def _probe_request(model: ClaudeAnsweringModel) -> dict:
    """The real request shape, with a trivially-small grounding."""
    g = GroundingContext(text="(probe) no real grounding.", artifacts_supplied=(), token_estimate=1)
    t = Task(prompt="Probe the endpoint.", proposed_action="do nothing")
    return model.build_request(SCAFFOLD, g, t)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Probe an Anthropic/LiteLLM endpoint.")
    ap.add_argument("--base-url", default=os.environ.get("ANTHROPIC_BASE_URL"))
    ap.add_argument("--key", default=os.environ.get("ANTHROPIC_API_KEY"))
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--skip-batch", action="store_true")
    args = ap.parse_args(argv)

    try:
        import anthropic
    except ImportError:
        print("need the anthropic SDK: pip install -e '.[real]'", file=sys.stderr)
        return 2
    if not args.key:
        print("set ANTHROPIC_API_KEY (the LiteLLM virtual key) or pass --key", file=sys.stderr)
        return 2

    client = anthropic.Anthropic(base_url=args.base_url or None, api_key=args.key)
    print(f"endpoint: {client.base_url}")
    print(f"model:    {args.model}\n")

    model = ClaudeAnsweringModel()
    req = _probe_request(model)
    req["model"] = args.model
    ok = True

    # 1. native messages.create + structured output
    print("[1/2] messages.create + structured output (output_config json_schema)…")
    try:
        resp = client.messages.create(**req)
        pc = model.parse_message(resp)              # the exact parse the benchmark uses
        u = usage_dict(getattr(resp, "usage", None))
        print(f"      PASS — parsed ProposedChange (asserts_permission={pc.asserts_permission}); "
              f"usage={u}")
        if u is None:
            print("      WARN — no usage reported; cost report would fall back to token estimates.")
    except Exception as exc:  # noqa: BLE001
        ok = False
        print(f"      FAIL — {type(exc).__name__}: {exc}")
        print("      The proxy isn't forwarding Anthropic structured outputs; scoring needs them.")
        print("      -> likely an OpenAI-compatible gateway, not an Anthropic passthrough.")

    # 2. Batch API
    if not args.skip_batch:
        print("\n[2/2] messages.batches.create + retrieve (the --batch path)…")
        try:
            b = client.messages.batches.create(
                requests=[{"custom_id": "probe", "params": req}])
            status = client.messages.batches.retrieve(b.id).processing_status
            print(f"      PASS — batch {b.id} accepted; status={status}")
            print("      (you can cancel it in the console; this probe doesn't wait for results.)")
        except Exception as exc:  # noqa: BLE001
            print(f"      FAIL — {type(exc).__name__}: {exc}")
            print("      Batch endpoint not proxied. Run the crossover synchronously through")
            print("      LiteLLM (drop --batch), or point --batch at a direct-Anthropic key.")

    print("\nverdict:")
    if ok:
        print("  ✓ Anthropic-native passthrough works — set ANTHROPIC_BASE_URL + the LiteLLM key")
        print("    and run as usual. Confirm the batch line above before using --batch.")
    else:
        print("  ✗ Not a transparent Anthropic passthrough — tell me and I'll add an")
        print("    OpenAI-compatible answering adapter (no batch, normalized JSON output).")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
