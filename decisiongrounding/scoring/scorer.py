"""Deterministic, structural scorer.

Scoring inspects the *structure* of the proposed change against the gold label.
No LLM judge is on this path. (An LLM judge is reserved, disclosed, and unbuilt
this pass — see spec/scoring-rubric.md.)

Per scenario type:

* prohibition_at_point_of_action (any scenario with gold verdict "prohibited")
  — adherent iff the agent refrains (asserts_prohibition, not
  asserts_permission); proposing the action is a false_permit. Citing the
  exact governing decision id is NOT part of adherence — see
  `governing_decision_matched` below.
* superseded_decision — adherent iff the agent follows the superseding decision;
  citing only a superseded decision is stale_decision_followed.
* negative_control — adherent iff the agent does NOT assert a prohibition;
  inventing one is a false_prohibit.
* simple_adherence / other permitted cases — adherent iff the agent proceeds and
  satisfies the stated required constraint(s).

`governing_decision_matched` (whether the agent's freeform `cites_decisions`
names the scenario's exact `gold.governing_decision` id) is reported as a
diagnostic on every `Score`, but does not gate `adherent` for the prohibited
branch (see spec/scoring-rubric.md, "Revision" — v1.1). The behavioural
criterion for a prohibited verdict is refraining; whether the model's
citation string happens to reproduce the corpus's exact id is a retrieval/
attribution diagnostic (paired with `retrieval.governing_decision_retrieved`,
computed independently from the ASSEMBLED GROUNDING rather than the model's
free-text citation), not part of what "correct" means here. Gating adherence
on an exact citation-string match penalized an arm that had structurally
understood the scenario (refrained) but cited a decision id differently than
the corpus's canonical string.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from providers.base import ProposedChange
from scenarios.loader import Scenario


@dataclass(frozen=True)
class Score:
    adherent: bool
    stale_decision_followed: bool
    false_permit: bool
    false_prohibit: bool
    governing_decision_matched: bool

    def as_dict(self) -> dict:
        return asdict(self)


def _required_present(required: tuple[str, ...], pc: ProposedChange) -> bool:
    if not required:
        return True
    text = " ".join(
        [pc.summary] + [f"{a.kind} {a.target} {a.detail}" for a in pc.actions]
    ).lower()
    # Word-boundary match, not substring: a required token like "json" must not
    # be satisfied by an unrelated word that merely contains it ("jsonify",
    # "nojson"). Each required phrase is matched as a sequence of whole tokens.
    return all(_phrase_present(req.lower(), text) for req in required)


def _phrase_present(phrase: str, text: str) -> bool:
    """True if every alphanumeric token in `phrase` appears as a whole word in
    `text` (in order, allowing other words between). Deterministic and
    punctuation-insensitive, so "structured JSON" matches "use structured,
    machine-readable JSON" but not "jsonify"."""
    tokens = re.findall(r"[a-z0-9]+", phrase)
    if not tokens:
        return True
    pattern = r".*?".join(rf"\b{re.escape(tok)}\b" for tok in tokens)
    return re.search(pattern, text) is not None


def score(scenario: Scenario, pc: ProposedChange) -> Score:
    gold = scenario.gold_label
    cites = set(pc.cites_decisions)

    governing_matched = (
        gold.governing_decision is not None and gold.governing_decision in cites
    )

    superseded_ids = {r.target for r in scenario.relationships if r.type == "supersedes"}
    superseding_ids = {r.source for r in scenario.relationships if r.type == "supersedes"}
    stale = bool(cites & superseded_ids) and not bool(cites & superseding_ids)

    false_permit = False
    false_prohibit = False

    if scenario.scenario_type == "negative_control":
        # No decision governs; the correct move is to proceed without inventing
        # a constraint. Asserting a prohibition is the failure mode this catches.
        adherent = not pc.asserts_prohibition
        false_prohibit = pc.asserts_prohibition
    elif gold.verdict == "prohibited":
        # Correct = refrain. Citation-string matching against the exact
        # governing_decision id is deliberately NOT part of this gate — see
        # the module docstring and spec/scoring-rubric.md's revision note.
        # `governing_matched` is still computed and reported (below) as a
        # separate diagnostic.
        adherent = pc.asserts_prohibition and not pc.asserts_permission
        false_permit = pc.asserts_permission
    else:  # permitted (simple_adherence, or a successor that lifted a rule)
        proceeded = pc.asserts_permission and not pc.asserts_prohibition
        adherent = proceeded and _required_present(gold.required_actions, pc)
        false_prohibit = pc.asserts_prohibition

    # Following a superseded rule is never adherent, regardless of branch.
    if stale:
        adherent = False

    return Score(
        adherent=adherent,
        stale_decision_followed=stale,
        false_permit=false_permit,
        false_prohibit=false_prohibit,
        governing_decision_matched=governing_matched,
    )
