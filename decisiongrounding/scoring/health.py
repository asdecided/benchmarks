"""Per-scenario discrimination / validity audit.

OpenAI's coding-eval analysis found ~20-30% of a popular benchmark's tasks were
broken — unsolvable, contaminated, or non-discriminating — silently capping the
ceiling. This audit surfaces the analogue for the crossover: for each scenario,
is it actually pulling its weight, or is it dead signal?

Four classes, referencing the two controls already in the sweep — the ceiling
arm (`context_dump`, sees the whole corpus) and the floor arm (`no_grounding`,
parametric memory only):

- **broken** — even the ceiling arm never adheres (likely mis-specified or
  unsolvable from the corpus).
- **contaminated** — the floor arm adheres (the model answers from pretraining
  memory, so the scenario doesn't test grounding — a real risk for public
  PEPs/RFCs; synthetic scenarios are contamination-proof by construction).
- **tie** — no arm separates from any other at any N (degenerate, no signal).
- **discriminating** — otherwise (grounding separates from the floor).

`unknown` when neither control arm is in the sweep. Pure and results-neutral:
reads only `dataset["per_scenario"]`.
"""

from __future__ import annotations

CEILING_ARM = "context_dump"
FLOOR_ARM = "no_grounding"
_ADHERE = 0.5  # majority; robust to multi-seed fractions and single-seed bools


def _adherence_by_n(per_scenario: dict, arm: str, sid: str) -> dict:
    """{N: adherence} for one (arm, scenario); adherent may be a bool
    (single-seed) or a fraction (multi-seed) — both coerce to float."""
    out = {}
    for rec in per_scenario.get(arm, {}).get(sid, []):
        v = rec.get("adherent")
        if v is not None:
            out[rec["N"]] = float(v)
    return out


def _adheres_somewhere(by_n: dict) -> bool:
    return any(v >= _ADHERE for v in by_n.values())


def scenario_health(dataset: dict) -> dict:
    """Classify every scenario in `dataset["per_scenario"]`.

    Returns::

        {"scenarios": [{"scenario_id", "class", "ceiling_adherent",
                        "floor_adherent", "separates", "max_gap"}, ...],
         "counts": {"discriminating", "broken", "contaminated", "tie",
                    "unknown"},
         "total": int,
         "controls": {"ceiling": bool, "floor": bool}}

    `.get`-guarded: a dataset without `per_scenario` yields an empty audit.
    """
    per = dataset.get("per_scenario") or {}
    arms = list(per)
    has_ceiling = CEILING_ARM in arms
    has_floor = FLOOR_ARM in arms
    sids = sorted({sid for arm in arms for sid in per.get(arm, {})})

    scenarios = []
    counts = {"discriminating": 0, "broken": 0, "contaminated": 0, "tie": 0, "unknown": 0}
    for sid in sids:
        by_arm = {arm: _adherence_by_n(per, arm, sid) for arm in arms}
        ns = sorted({n for b in by_arm.values() for n in b})

        # Between-arm separation: the largest adherence gap at any shared N.
        max_gap = 0.0
        for n in ns:
            vals = [b[n] for b in by_arm.values() if n in b]
            if len(vals) >= 2:
                max_gap = max(max_gap, max(vals) - min(vals))
        separates = max_gap > 1e-9

        ceiling_adherent = _adheres_somewhere(by_arm[CEILING_ARM]) if has_ceiling else None
        floor_adherent = _adheres_somewhere(by_arm[FLOOR_ARM]) if has_floor else None

        if not (has_ceiling or has_floor):
            cls = "unknown"
        elif has_ceiling and not ceiling_adherent:
            cls = "broken"
        elif has_floor and floor_adherent:
            cls = "contaminated"
        elif not separates:
            cls = "tie"
        else:
            cls = "discriminating"

        counts[cls] += 1
        scenarios.append({
            "scenario_id": sid, "class": cls,
            "ceiling_adherent": ceiling_adherent, "floor_adherent": floor_adherent,
            "separates": separates, "max_gap": max_gap,
        })

    return {
        "scenarios": scenarios,
        "counts": counts,
        "total": len(sids),
        "controls": {"ceiling": has_ceiling, "floor": has_floor},
    }
