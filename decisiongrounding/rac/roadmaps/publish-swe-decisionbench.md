---
schema_version: 1
id: DG-KVPW3E3J2A79
type: roadmap
tags: [publication, paper, arxiv]
---
# Publish SWE-DecisionBench (arXiv preprint)

## Outcomes

- A credible, reproducible **preprint** that positions SWE-DecisionBench beside
  SWE-ContextBench and answers the headline question with real data.
- A results→paper pipeline so the paper's figures never drift from the numbers.
- An honest result published in either direction (the pre-registered falsifier
  governs the narrative, not the desired outcome).

## Initiatives

- **Paper scaffold** — `paper/` LaTeX (sections drafted from the README, ADRs,
  and `spec/`), name as a swappable `\benchname` macro. *(done)*
- **Figure pipeline** — `scripts/paper_figs.py` + `make paper-figs` emit
  paper-ready figures (PDF via the `[chart]` extra, else SVG) from the crossover
  dataset. *(done)*
- **Funded data run** — produce the real adherence-vs-N crossover + report (the
  data-provision PR); fill the results/figures/verdict into the paper.
- **Strengthen the claim** — multiple seeds for variance, and ideally 2–3
  answering models, before a strong empirical statement.
- **Submit** — resolve arXiv endorsement / affiliated submitter, pick a template,
  and post the preprint.

## Success Measures

- `make paper-figs` produces the figures and `make paper` builds `main.pdf`.
- Every `\todo` in `paper/` is resolved (results, counts, model/seed strings,
  citation verification, archived dataset DOI/release).
- The reported numbers match the committed `results/published/` dataset and report.

## Assumptions

- Funded model access is available for the real run (direct or via a proxy).
- The benchmark + methodology genre is a sufficient contribution for a preprint;
  breadth (many models) can follow.

## Risks

- **Thin data.** One model / ~19 scenarios / one seed is weak for a headline
  empirical claim — mitigated by framing as methodology + pilot and adding
  seeds/models.
- **Submission gate.** First-time cs submitters need an arXiv endorsement; sort an
  affiliated co-author or endorsement early.
- **Narrative risk.** If the falsifier triggers, the paper becomes an honest
  limited-effect result — acceptable and arguably more credible.

## Related Decisions

- DG-KVPW3XG9TDZY
- DG-KVMRSS0C7T4M
