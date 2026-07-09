# External Scenario Request — graded lexical overlap (companion brief)

An **additive companion** to `external-scenario-request.md` (unchanged). That
brief asks a blind third-party author for real decision-adherence scenarios;
this one adds a single dimension the roster expansion needs: **graded lexical
overlap** between the task vocabulary and the distractor domain.

Use this brief when commissioning scenarios specifically to test whether
lexical retrieval collapses at scale, rather than in one over-lexical case (the
pilot's `prohibition_language_migration` produced 12 of 13 failures because its
vocabulary saturated the PEP-title distractor pool).

## What to add to the base brief

Everything in `external-scenario-request.md` still applies — real public
documents only, gold labels set blind, the two authorable discriminating types
(`superseded_decision`, `prohibition_at_point_of_action`), and the returned
JSON shape. Add the following requirement:

> **Declare each scenario's lexical overlap.** For every scenario, add a
> `"lexical_overlap"` field with one of `"high"`, `"medium"`, `"low"`,
> describing how much the *task's* wording overlaps the *topic vocabulary of
> the document family the distractors are drawn from* (for the Python/PEP pool:
> Python-language, packaging, typing, and standard-library terms).
>
> - **high** — the task is phrased in the distractor domain's own vocabulary
>   (e.g. "rewrite the module's type annotations to the new typing syntax").
> - **medium** — a mix of domain vocabulary and task-specific terms.
> - **low** — the task uses domain-external vocabulary (warehouse, invoicing,
>   badge access, DNS cutover, payroll) that rarely appears in the distractor
>   titles.
>
> Aim for a spread: request **5–10 scenarios covering all three bands across
> both discriminating types**, so the accepted subset can fill the type × band
> matrix.

## Acceptance (our side, not the author's)

On acceptance we verify the declared band against a measurement:
`scenarios/overlap.py::measured_overlap` scores the task against the pinned
distractor pool and `overlap_band` maps it to high/medium/low. A declared band
that does not match the measured band is sent back for revision — the band is a
**measured property**, not a self-assigned label.

## Roster-freeze rule (unchanged, restated)

Accepted scenarios enter `scenarios_real/` **only** as a deliberate
pre-registration event: together with a `tests/test_real_roster.py`
`PINNED_ROSTER` update and a new analysis-plan amendment (amendment-1 is
frozen; see `analysis-plan-amendment-1.md`). Candidate edges staged for this
expansion are listed in `../docs/real-scenario-candidates.md`; they carry no
`scenario.json` until a blind gold label is authored and the offline gate
passes.
