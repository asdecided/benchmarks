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

If the gateway exposes only the OpenAI-compatible surface (structured outputs
FAIL in native mode), probe that instead — it exercises the exact request the
`litellm:<alias>` answering backend sends:

    LITELLM_BASE_URL=https://your-litellm  LITELLM_API_KEY=sk-... \
    python -m scripts.litellm_probe --mode openai --model <alias>
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
    # Defaults resolve per --mode below: native reads ANTHROPIC_*, openai reads
    # LITELLM_*/OPENAI_* — a flag here always wins over either.
    ap.add_argument("--base-url", default=None)
    ap.add_argument("--key", default=None)
    ap.add_argument("--model", default="claude-opus-4-8")
    ap.add_argument("--skip-batch", action="store_true")
    ap.add_argument(
        "--mode",
        choices=("native", "openai"),
        default="native",
        help="native: Anthropic /v1/messages passthrough; openai: the gateway's "
        "OpenAI-compatible /chat/completions surface (the litellm:<alias> backend).",
    )
    args = ap.parse_args(argv)

    if args.mode == "openai":
        return _probe_openai(args)

    try:
        import anthropic
    except ImportError:
        print("need the anthropic SDK: pip install -e '.[real]'", file=sys.stderr)
        return 2
    base_url = args.base_url or os.environ.get("ANTHROPIC_BASE_URL")
    key = args.key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        print("set ANTHROPIC_API_KEY (the LiteLLM virtual key) or pass --key", file=sys.stderr)
        return 2

    client = anthropic.Anthropic(base_url=base_url or None, api_key=key)
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
        print("  ✗ Not a transparent Anthropic passthrough. Probe the OpenAI-compatible")
        print("    surface instead:  python -m scripts.litellm_probe --mode openai")
        print("    and run with  --answering litellm:<model-alias>  (synchronous only —")
        print("    no Batch API on that surface).")
    return 0 if ok else 1


def _probe_openai(args) -> int:
    """Probe an OpenAI-compatible gateway with the litellm backend's request."""
    import os as _os

    from providers.answering import OpenAICompatAnsweringModel

    if args.base_url:
        _os.environ["LITELLM_BASE_URL"] = args.base_url
    if args.key:
        _os.environ["LITELLM_API_KEY"] = args.key

    model = OpenAICompatAnsweringModel(model=args.model)
    print(f"endpoint: {model._base_url()}/chat/completions")
    print(f"model:    {args.model}\n")

    g = GroundingContext(text="(probe) no real grounding.", artifacts_supplied=(), token_estimate=1)
    t = Task(prompt="Probe the endpoint.", proposed_action="do nothing")
    print("[1/1] chat/completions + response_format json_schema…")
    try:
        pc = model.respond(SCAFFOLD, g, t)
        print(
            f"      PASS — parsed ProposedChange (asserts_permission={pc.asserts_permission}); "
            f"usage={model.last_usage}"
        )
        if model.last_usage is None:
            print("      WARN — no usage reported; cost report would fall back to estimates.")
        print("\nverdict:")
        print("  ✓ OpenAI-compatible surface works — run with:")
        print(f"      --answering litellm:{args.model}")
        print("    Synchronous only: --batch / make real-batch need a direct-Anthropic key.")
        print("    Pin the gateway alias to a fixed model, or the recorded model identity")
        print("    in reports is misleading.")
        return 0
    except Exception as exc:  # noqa: BLE001
        print(f"      FAIL — {type(exc).__name__}: {exc}")
        print("\nverdict:")
        print("  ✗ The gateway rejected the structured-output request. Scoring needs")
        print("    schema-enforced JSON; check the alias supports response_format")
        print("    json_schema (LiteLLM translates it per backend).")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
