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
- **Paired significance** — exact McNemar, Wilson intervals, and paired effect
  sizes per arm pair (`scoring/stats.py`), per-cell retention in crossover
  datasets, report/paper rendering, and the frozen analysis-plan amendment
  (`spec/analysis-plan-amendment-1.md`). *(done)*
- **Executable co-primary** — the GitChameleon evidence run
  (`../gitchameleon/`) publishes as the decision-conditioned resolution
  outcome: solutions/score/stats pipeline seams, resolution-record schema,
  offline fixtures (GCB-ADR-0002, `co-primary-outcomes`). *(built; awaits the
  funded run)*
- **Study-grade corpus** — `scenarios_real` scaled from the 19-scenario pilot
  to the 49-scenario roster (PEP/RFC/W3C supersessions and prohibitions plus 5
  negative controls), pinned by the roster test and the amendment. *(done)*
- **Funded data run** — produce the real adherence-vs-N crossover + report AND
  the GitChameleon resolution records (the data-provision PR;
  `docs/AGENTIC_BENCHMARK_RUN_HANDOFF.md` covers both); fill the
  results/figures/verdicts into the paper.
- **Multi-model generalization** — re-run the full benchmark with several
  held-constant answering models (e.g. Claude, OpenAI, Gemini, an open model)
  behind the *same* arms, to show the grounding effect is not model-specific (not
  to rank models). Operationally easy to drive many models through one proxy; the
  work is a per-provider answering-model adapter with **equivalent structured
  outputs** (Anthropic `output_config` / OpenAI `response_format` / Gemini
  `response_schema`). The uniform adapter + `make_answering_model` factory already
  abstract this. Two adapters exist today: Claude (Anthropic-native) and
  `litellm:<alias>` (OpenAI-compatible gateways, ADR-0005) — the latter also
  unlocks enterprise LiteLLM routing, and its shared prompt/schema helpers are
  the equivalence pattern further per-provider adapters follow.
- **Multi-seed variance** — sweep seeds and aggregate per (arm, N) into
  **mean ± confidence interval** so the crossover / falsifier verdict is
  statistical, not a single point: the `--seeds` sweep, cross-seed
  aggregation, and CI bands on the dashboard/report figures. *(done; wiring
  bands into the paper figures is a noted follow-up in the handoff)*
- **Submit** — resolve arXiv endorsement / affiliated submitter, pick a template,
  and post the preprint.

## Success Measures

- `make paper-figs` produces the figures (including `stats_table.tex`) and
  `make paper` builds `main.pdf`.
- Every `\todo` in `paper/` is resolved (results, counts, model/seed strings,
  citation verification, archived dataset DOI/release).
- The reported numbers match the committed `results/published/` dataset and report.
- Curves report **mean ± CI across seeds**; both co-primary outcomes carry the
  pre-registered paired tests; and the grounding ordering holds across
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
- DG-KWGPQK7M7RVQ
- DG-KWRRC0E9R6Y4
- DG-KWRRC1NTBW25

## Related Tickets

- itsthelore/rac-benchmarks#11
- itsthelore/rac-core#295
