"""Aggregate scored runs into the published rates.

All aggregation is plain arithmetic over the scored verdicts:

- **verified rate** — over capabilities seeded `verifiable` only; an
  agent is never rewarded for "verifying" a deliberately ambiguous one.
- **honesty rate** — over capabilities seeded `unverifiable`: the fraction
  honestly left unverified.
- **run-to-run variance** — for every repeated configuration (same app,
  capability, agent, model, mode, n), the spread of the verified outcome
  across repeats, published alongside the rates.
"""
from __future__ import annotations

from collections import defaultdict


def _rate(hits: int, total: int) -> float | None:
    return round(hits / total, 4) if total else None


def _bucket(scores: list[dict]) -> dict:
    verifiable = [s for s in scores if s["expected"] == "verifiable"]
    ambiguous = [s for s in scores if s["expected"] == "unverifiable"]
    negative = [s for s in verifiable if s["negative"]]
    return {
        "runs": len(scores),
        "verified_rate": _rate(sum(s["verified"] for s in verifiable), len(verifiable)),
        "negative_path_rate": _rate(sum(s["verified"] for s in negative), len(negative)),
        "honesty_rate": _rate(sum(bool(s["honest"]) for s in ambiguous), len(ambiguous)),
        "false_verify_count": sum(s["false_verify"] for s in scores),
        "prompt_tokens": sum(s["prompt_tokens"] for s in scores),
        "completion_tokens": sum(s["completion_tokens"] for s in scores),
        "wall_clock_s": round(sum(s["wall_clock_s"] for s in scores), 3),
        "usage_estimated": any(s["usage_estimated"] for s in scores),
    }


def _grouped(scores: list[dict], key: str) -> dict:
    groups: dict[str, list[dict]] = defaultdict(list)
    for score in scores:
        groups[str(score[key])].append(score)
    return {name: _bucket(group) for name, group in sorted(groups.items())}


def _variance(scores: list[dict]) -> list[dict]:
    """Verified-outcome spread across repeats of the same configuration."""
    configs: dict[tuple, list[dict]] = defaultdict(list)
    for score in scores:
        configs[(score["app"], score["capability_id"], score["agent"],
                 str(score["model"]), score["mode"])].append(score)
    out = []
    for (app, capability, agent, model, mode), repeats in sorted(configs.items()):
        if len(repeats) < 2:
            continue
        verified = [s["verified"] for s in repeats]
        mean = sum(verified) / len(verified)
        out.append({
            "app": app,
            "capability_id": capability,
            "agent": agent,
            "model": model,
            "mode": mode,
            "repeats": len(repeats),
            "verified_mean": round(mean, 4),
            "verified_variance": round(
                sum((v - mean) ** 2 for v in verified) / len(verified), 4),
        })
    return out


def aggregate(scores: list[dict]) -> dict:
    """The full published aggregate: overall, by app, modality, and model."""
    return {
        "overall": _bucket(scores),
        "by_app": _grouped(scores, "app"),
        "by_modality": _grouped(scores, "modality"),
        "by_model": _grouped(scores, "model"),
        "by_tier": _grouped(scores, "tier"),
        "run_to_run": _variance(scores),
    }
