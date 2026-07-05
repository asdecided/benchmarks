# Analysis Plan — Amendment 1 (FROZEN — pre-registration)

An **additive** amendment to the frozen pre-registration
(`scenario-taxonomy.md`, `scoring-rubric.md` — both unchanged; the taxonomy's
own rule applies here too: changing this document is a new spec version, not
an edit). It pre-registers the confirmatory statistical analysis and the
second co-primary outcome for the publication study (SWE-DecisionBench;
rac-core `rac-grounding-baseline-study` REQ-002/003/005), before the funded
runs it governs exist.

## Disclosure — what was known when this was frozen

The base-N headline compare
(`../results/published/2026-06-20-headline-opus-4-8-voyage.md`, 19 scenarios,
seed 0) **was known** when this amendment was written: grounding decisive
(0.95 vs 0.00), all grounded arms tied at base N, as the frozen taxonomy
predicted. The following did **not** exist and are the confirmatory subjects
of this plan: any real adherence-vs-N crossover, any multi-seed real run, any
run over the scaled 49-scenario roster, and any GitChameleon resolution
result. The previously published falsifier ("grounded ≈ `naive_rag` on
superseded + prohibition at N ≥ 50", stated in the README and the paired-CI
form in `../rac/decisions/variance-reporting.md`) is not redefined; this
amendment layers the exact test that adjudicates it and keeps the seed-level
CI as supporting evidence.

## Hypotheses

- **H1 (decision adherence, structural co-primary).** Typed,
  supersession-aware retrieval (`rac`) yields higher decision-adherence than
  embedding retrieval (`naive_rag`) on the discriminating scenarios once the
  governing decision is buried among real distractors.
- **H2 (decision-conditioned resolution, executable co-primary).** Grounding
  in the recorded version-pin decision (`rac`) yields a higher upstream-test
  pass rate than `no_grounding` on the GitChameleon evidence run under the
  no-version-in-prompt protocol (`../../gitchameleon/`, GCB-ADR-0002).

Co-primary means each claim stands alone; the conjunction is claimed only if
both hold. A mixed outcome is a publishable finding, reported plainly.

## Paired design and units

Arms answer identical scenarios under common random numbers (same corpus,
same distractor draw per (N, seed)), so all comparisons are paired:

- Base-N compare: paired by **scenario** (n = 49).
- Crossover sweep: paired by **scenario × seed** within each N
  (44 discriminating scenarios × 5 seeds; negative controls are base-N only,
  per the frozen taxonomy's `DISCRIMINATING` filter).
- Resolution: paired by **example** (GitChameleon example_id).

## Tests and effect sizes (all deterministic; `../scoring/stats.py`)

Per arm pair and outcome:

- **Exact McNemar** — two-sided binomial on the discordant counts (b, c); no
  chi-square approximation, no continuity correction; b + c = 0 is reported
  `degenerate`, not tested.
- **Paired risk difference** with a Wald 95% interval.
- **Conditional odds ratio** b/c with a Wilson-transformed 95% interval;
  zero-cell tables reported `degenerate`, never Haldane-smoothed.
- **Wilson 95% intervals** on marginal rates.
- The seed-level t-based CI on the paired `rac − naive_rag` difference
  (`variance-reporting`) is retained as supporting variance evidence.

## Confirmatory and secondary analyses

- **H1 confirmatory:** `rac` vs `naive_rag`, outcome `adherent`, at
  **N = 300**, α = 0.05 (two-sided exact McNemar). H1 is falsified if this
  test is not significant in `rac`'s favour (or the cell is degenerate with
  the rates tied).
- **H1 secondary:** the same pair at N ∈ {50, 150}, Holm-corrected. N = 10 is
  descriptive only — the frozen taxonomy pre-declares base-N an expected tie.
- **H2 confirmatory:** `rac` vs `no_grounding`, outcome `passed`, over all
  scored examples, α = 0.05. H2 is falsified if not significant in `rac`'s
  favour. `rac` vs `naive_rag` on `passed` is secondary (it requires the
  embedder pin recorded at run time).
- All other pairs and outcomes (`stale_decision_followed`, `false_permit`,
  governing recall) are reported context, uncorrected and labelled as such.

## What these statistics are not

Analysis only. No p-value, interval, or effect size enters any CI gate or
scored path (rac-core ADR-066 / ADR-097); the headline metric remains the
single decision-adherence rate, and the scoring rubric's "no composite" rule
is untouched — these are inferential statistics *about* the scores, not
scores.

## Frozen scenario roster

The `scenarios_real/` roster for the study is exactly the 49 scenario ids
below (24 PEP: 19 supersessions, 2 prohibitions, 3 negative controls; 21 RFC:
12 supersessions, 7 prohibitions, 2 negative controls; 4 W3C edition
supersessions). `tests/test_real_roster.py` pins the same list; adding,
removing, or renaming a scenario after this freeze is a new spec version and
must say so in review. Gold labels were authored blind to any arm output; no
real run had been executed on any of the 30 newly added scenarios when this
amendment was frozen.

pep8_none_identity_prohibition, peps_annotations_supersession,
peps_dbapi_supersession, peps_dict_version_supersession,
peps_enum_supersession, peps_exception_context_supersession,
peps_fd_inheritance_supersession, peps_backcompat_policy_supersession,
peps_local_version_prohibition, peps_manylinux_supersession,
peps_metadata_supersession, peps_finally_exit_supersession,
peps_micro_release_supersession, peps_pattern_matching_supersession,
peps_pypi_hosting_supersession, peps_script_deps_supersession,
peps_string_interpolation_supersession, peps_style_negative_control,
peps_subinterpreters_supersession, peps_timezone_supersession,
peps_typing_negative_control, peps_version_supersession,
peps_wsgi_supersession, peps_zen_negative_control,
rfc_content_length_te_prohibition, rfc_cookies_supersession,
rfc_date_header_prohibition, rfc_email_format_supersession,
rfc_http_messaging_supersession, rfc_http_semantics_supersession,
rfc_imap_supersession, rfc_json_bom_prohibition, rfc_json_supersession,
rfc_keywords_negative_control, rfc_language_tags_supersession,
rfc_md5_prohibition, rfc_ntp_supersession, rfc_rc4_prohibition,
rfc_smtp_supersession, rfc_sslv3_prohibition,
rfc_timestamps_negative_control, rfc_tls_identity_supersession,
rfc_tls_legacy_prohibition, rfc_tls_version_supersession,
rfc_uri_supersession, w3c_xhtml_edition_supersession,
w3c_xml_edition_supersession, w3c_xml_names_edition_supersession,
w3c_xpath_edition_supersession

## Run parameters (pre-registered)

- N grid: {10, 50, 150, 300} (frozen in the taxonomy); 5 seeds (0–4), common
  random numbers across arms; seeds may be extended (append-only
  `--augment`) only at N where the confirmatory or secondary cells are
  degenerate, and the extension is disclosed.
- Answering model pinned (`claude-opus-4-8` or the recorded gateway alias);
  `naive_rag` embedder pinned and recorded with the run.
- GitChameleon: dataset revision, upstream-harness commit, and model pin
  recorded with the resolution records
  (`../../gitchameleon/schema/resolution_record.schema.json`).
