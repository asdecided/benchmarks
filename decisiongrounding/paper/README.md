# SWE-DecisionBench — paper

LaTeX source for the preprint. The benchmark name is a single macro
(`\benchname` in `main.tex`), so it is trivially swappable.

## Build

```bash
# 1. figures from the crossover dataset (PDF needs the [chart] extra; else SVG)
make paper-figs                                   # -> paper/figures/*.pdf
make paper-figs CROSSOVER=results/run-...-crossover.json   # a specific dataset

# 2. the PDF (needs a LaTeX toolchain: pdflatex + bibtex)
make paper                                        # -> paper/main.pdf
```

## Status

The prose sections are drafted from the repository (README, ADRs, `spec/`,
`CONTRIBUTING.md`). Everything awaiting the funded run or external verification is
marked in red with `\todo{...}` — search for `\todo` to find every gap:

- results/figures interpretation and the falsifier outcome,
- final scenario/repository counts, model/embedder/seed strings,
- citation verification (e.g. MemoryBench), and the archived dataset DOI/release.

Figures are **not** committed (`.gitignore`d) — they are regenerated from the
dataset so they never drift from the numbers.
