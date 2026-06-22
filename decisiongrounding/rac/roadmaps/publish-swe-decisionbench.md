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
- **Multi-model generalization** — re-run the full benchmark with several
  held-constant answering models (e.g. Claude, OpenAI, Gemini, an open model)
  behind the *same* arms, to show the grounding effect is not model-specific (not
  to rank models). Operationally easy to drive many models through one proxy; the
  work is a per-provider answering-model adapter with **equivalent structured
  outputs** (Anthropic `output_config` / OpenAI `response_format` / Gemini
  `response_schema`). The uniform adapter + `make_answering_model` factory already
  abstract this; only the Claude adapter exists today.
- **Multi-seed variance** — sweep seeds and aggregate per (arm, N) into
  **mean ± confidence interval** so the crossover / falsifier verdict is
  statistical, not a single point. Needs harness support: a `--seeds` sweep,
  cross-seed aggregation, and CI bands on the figures (the part most worth
  building, since the answering model is stochastic even at pinned temperature).
- **Submit** — resolve arXiv endorsement / affiliated submitter, pick a template,
  and post the preprint.

## Success Measures

- `make paper-figs` produces the figures and `make paper` builds `main.pdf`.
- Every `\todo` in `paper/` is resolved (results, counts, model/seed strings,
  citation verification, archived dataset DOI/release).
- The reported numbers match the committed `results/published/` dataset and report.
- Curves report **mean ± CI across seeds**, and the grounding ordering holds across
  **≥2 answering models** (the generalization claim).

## Assumptions

- Funded model access is available for the real run (direct or via a proxy).
- The benchmark + methodology genre is a sufficient contribution for a preprint;
  breadth (many models) can follow.

## Risks

- **Thin data.** One model / ~19 scenarios / one seed is weak for a headline
  empirical claim — mitigated by framing as methodology + pilot and adding
  seeds/models. Multi-model is cheap to drive (one proxy, many models); multi-seed
  and per-provider adapters are the engineering, and cost multiplies with both.
- **Submission gate.** First-time cs submitters need an arXiv endorsement; sort an
  affiliated co-author or endorsement early.
- **Narrative risk.** If the falsifier triggers, the paper becomes an honest
  limited-effect result — acceptable and arguably more credible.

## Related Decisions

- DG-KVPW3XG9TDZY
- DG-KVMRSS0C7T4M
