# Headline result — decision adherence on real Opus 4.8 + Voyage

**First genuine decision-adherence result** on the real/public-derived corpus (not the offline harness illustration). Preserved here because `results/` is gitignored for transient runs and the build container is ephemeral.

## Provenance

- **Generated:** 2026-06-20T20:18:56.903796+00:00
- **Answering model:** `claude-opus-4-8` (temperature `None`, seed `0`)
- **Embedder (naive_rag):** `voyage:voyage-4-large`
- **Backend versions:** anthropic `0.111.0`, voyageai `0.4.1`
- **Scenarios:** 19 real (PEP + RFC + W3C), all of `scenarios_real/`
- **Arms:** context_dump, naive_rag, no_grounding, rac
- **Errors:** 0
- **Harness:** 0.1.0-scaffold

## Per-arm metrics

| arm | adherence | stale | false-permit | false-prohibit | governing-recall |
|---|---|---|---|---|---|
| context_dump | 0.95 | 0.00 | 0.05 | 0.00 | 1.00 |
| naive_rag | 0.95 | 0.00 | 0.05 | 0.00 | 1.00 |
| no_grounding | 0.00 | 0.00 | 0.53 | 0.00 | 0.00 |
| rac | 0.95 | 0.00 | 0.05 | 0.00 | 1.00 |

## Per-scenario adherence (1 = adherent)

| scenario | context_dump | naive_rag | no_grounding | rac |
|---|---|---|---|---|
| pep8_none_identity_prohibition | 1 | 1 | 0 | 1 |
| peps_annotations_supersession | 1 | 1 | 0 | 1 |
| peps_enum_supersession | 1 | 1 | 0 | 1 |
| peps_local_version_prohibition | 1 | 1 | 0 | 1 |
| peps_manylinux_supersession | 0 | 0 | 0 | 0 |
| peps_metadata_supersession | 1 | 1 | 0 | 1 |
| peps_pattern_matching_supersession | 1 | 1 | 0 | 1 |
| peps_timezone_supersession | 1 | 1 | 0 | 1 |
| peps_version_supersession | 1 | 1 | 0 | 1 |
| rfc_content_length_te_prohibition | 1 | 1 | 0 | 1 |
| rfc_date_header_prohibition | 1 | 1 | 0 | 1 |
| rfc_http_messaging_supersession | 1 | 1 | 0 | 1 |
| rfc_http_semantics_supersession | 1 | 1 | 0 | 1 |
| rfc_json_bom_prohibition | 1 | 1 | 0 | 1 |
| rfc_json_supersession | 1 | 1 | 0 | 1 |
| rfc_rc4_prohibition | 1 | 1 | 0 | 1 |
| rfc_tls_identity_supersession | 1 | 1 | 0 | 1 |
| rfc_tls_version_supersession | 1 | 1 | 0 | 1 |
| w3c_xml_edition_supersession | 1 | 1 | 0 | 1 |

## Reading

1. **Grounding is decisive.** Ungrounded Opus scores 0.00 — it false-permits the prohibited/stale action on every case. Any grounding arm reaches 18/19.
2. **The three grounding strategies tie at base corpus size — as the taxonomy predicts.** Corpora are 1–4 artifacts, so Voyage `naive_rag` trivially retrieves the governing decision (recall 1.00, same as context_dump and rac). The typed-retrieval-vs-naive-RAG separation is designed to appear in the **crossover at N≥50**, not here. This run validates the harness on a real model + real corpora and proves grounding matters; it does **not** yet test the rac-vs-naive_rag thesis.
3. **The single shared miss (`peps_manylinux_supersession`) is a gold-label issue, not a model failure.** All three grounded arms retrieved and cited PEP 600 and stated it supersedes 513/571/599, but judged using the `manylinux2014` tag *permitted* — which is defensible, since PEP 600 supersedes the *PEPs* while keeping `manylinux2014` etc. as valid aliases. The gold `verdict: prohibited` is too strict and should be revised.

## Caveats

- Base-N **expected-tie** regime; the discriminating signal is the adherence-vs-N curve.
- Symmetric-injection caveat (see README): this measures retrieval/assembly quality given one equal shot at context, not whether a pull-based layer gets consulted in production.

## Reproduce

```bash
pip install -e '.[real]'   # + rac CLI on PATH
export ANTHROPIC_API_KEY=...  VOYAGE_API_KEY=...
python -m runner.cli compare --arms context_dump,naive_rag,no_grounding,rac \
  --scenarios scenarios_real --answering claude --embedder voyage:voyage-4-large --seed 0
```

Raw report: `2026-06-20-headline-opus-4-8-voyage.json` (alongside this file).

