.PHONY: demo test compare pool rfc-pool crossover-real corpora-verify real-run real-crossover ui dashboard paper-figs paper

# Local web UI: serve the results dashboard at 127.0.0.1:8099 (needs the [ui]
# extra: pip install -e '.[ui]'). RESULTS overrides the directory it reads.
ui:
	python -m runner.cli ui --results $(or $(RESULTS),results/published) --port $(or $(PORT),8099)
# Static snapshot of the dashboard (bakes in the offline cost-vs-N curve):
dashboard:
	python -m scripts.dashboard --run $(RUN) --crossover $(CROSSOVER) --cost-curve \
	  --out results/published/index.html

# The real evidence run. Needs ANTHROPIC_API_KEY (+ VOYAGE_API_KEY recommended).
# headline compare across all real scenarios:
real-run:
	./scripts/run_real.sh
# same headline via the Batch API (~50% of standard price; asynchronous):
real-batch:
	BATCH=1 ./scripts/run_real.sh
# compare + the adherence-vs-N crossover over a real pool (set NS to taste; add
# BATCH=1 for the Batch API, and SEEDS=0-4 for mean +/- CI error bars). The
# default arms include rac + no_grounding, so both signal-to-noise contrasts
# (rac-vs-naive_rag, rac-vs-no_grounding) populate; SEEDS>=2 is REQUIRED for the
# signal-to-noise section (noise cannot be estimated from a single seed):
real-crossover:
	CROSSOVER=1 ./scripts/run_real.sh

# The one working comparison: two real arms, four worked scenarios, offline.
demo:
	python -m runner.cli demo

# Run a single named comparison, e.g. make compare ARMS=context_dump,naive_rag
compare:
	python -m runner.cli compare --arms $(ARMS)

# Build the real distractor pools from their pins (one network pass each:
# ~644 PEPs, ~1125 RFCs). Pick the one matching your scenarios' domain.
pool:
	python -m ingest.peps pool build

rfc-pool:
	python -m ingest.rfcs pool build

# Verify every real scenario corpus reproduces from its pin (network).
corpora-verify:
	python -m ingest.peps verify --out scenarios_real/pep8_none_identity_prohibition
	python -m ingest.peps verify --out scenarios_real/peps_annotations_supersession
	python -m ingest.peps verify --out scenarios_real/peps_dbapi_supersession
	python -m ingest.peps verify --out scenarios_real/peps_dict_version_supersession
	python -m ingest.peps verify --out scenarios_real/peps_enum_supersession
	python -m ingest.peps verify --out scenarios_real/peps_exception_context_supersession
	python -m ingest.peps verify --out scenarios_real/peps_fd_inheritance_supersession
	python -m ingest.peps verify --out scenarios_real/peps_backcompat_policy_supersession
	python -m ingest.peps verify --out scenarios_real/peps_local_version_prohibition
	python -m ingest.peps verify --out scenarios_real/peps_manylinux_supersession
	python -m ingest.peps verify --out scenarios_real/peps_metadata_supersession
	python -m ingest.peps verify --out scenarios_real/peps_finally_exit_supersession
	python -m ingest.peps verify --out scenarios_real/peps_micro_release_supersession
	python -m ingest.peps verify --out scenarios_real/peps_pattern_matching_supersession
	python -m ingest.peps verify --out scenarios_real/peps_pypi_hosting_supersession
	python -m ingest.peps verify --out scenarios_real/peps_script_deps_supersession
	python -m ingest.peps verify --out scenarios_real/peps_string_interpolation_supersession
	python -m ingest.peps verify --out scenarios_real/peps_style_negative_control
	python -m ingest.peps verify --out scenarios_real/peps_subinterpreters_supersession
	python -m ingest.peps verify --out scenarios_real/peps_timezone_supersession
	python -m ingest.peps verify --out scenarios_real/peps_typing_negative_control
	python -m ingest.peps verify --out scenarios_real/peps_version_supersession
	python -m ingest.peps verify --out scenarios_real/peps_wsgi_supersession
	python -m ingest.peps verify --out scenarios_real/peps_zen_negative_control
	python -m ingest.rfcs verify --out scenarios_real/rfc_content_length_te_prohibition
	python -m ingest.rfcs verify --out scenarios_real/rfc_cookies_supersession
	python -m ingest.rfcs verify --out scenarios_real/rfc_date_header_prohibition
	python -m ingest.rfcs verify --out scenarios_real/rfc_email_format_supersession
	python -m ingest.rfcs verify --out scenarios_real/rfc_http_messaging_supersession
	python -m ingest.rfcs verify --out scenarios_real/rfc_http_semantics_supersession
	python -m ingest.rfcs verify --out scenarios_real/rfc_imap_supersession
	python -m ingest.rfcs verify --out scenarios_real/rfc_json_bom_prohibition
	python -m ingest.rfcs verify --out scenarios_real/rfc_json_supersession
	python -m ingest.rfcs verify --out scenarios_real/rfc_keywords_negative_control
	python -m ingest.rfcs verify --out scenarios_real/rfc_language_tags_supersession
	python -m ingest.rfcs verify --out scenarios_real/rfc_md5_prohibition
	python -m ingest.rfcs verify --out scenarios_real/rfc_ntp_supersession
	python -m ingest.rfcs verify --out scenarios_real/rfc_rc4_prohibition
	python -m ingest.rfcs verify --out scenarios_real/rfc_smtp_supersession
	python -m ingest.rfcs verify --out scenarios_real/rfc_sslv3_prohibition
	python -m ingest.rfcs verify --out scenarios_real/rfc_timestamps_negative_control
	python -m ingest.rfcs verify --out scenarios_real/rfc_tls_identity_supersession
	python -m ingest.rfcs verify --out scenarios_real/rfc_tls_legacy_prohibition
	python -m ingest.rfcs verify --out scenarios_real/rfc_tls_version_supersession
	python -m ingest.rfcs verify --out scenarios_real/rfc_uri_supersession
	python -m ingest.w3c  verify --out scenarios_real/w3c_xhtml_edition_supersession
	python -m ingest.w3c  verify --out scenarios_real/w3c_xml_edition_supersession
	python -m ingest.w3c  verify --out scenarios_real/w3c_xml_names_edition_supersession
	python -m ingest.w3c  verify --out scenarios_real/w3c_xpath_edition_supersession

# Real adherence-vs-N curve over the real PEP pool. Offline by default
# (illustration); add ANSWERING=claude EMBEDDER=voyage:voyage-4-large + keys for
# the real result. NS keeps API spend tunable, e.g. NS=10,50.
crossover-real:
	python -m runner.cli demo --scenarios scenarios_real \
	  --arms context_dump,naive_rag,no_grounding,rac \
	  --distractors real --ns $(or $(NS),10,50,150,300) \
	  --answering $(or $(ANSWERING),offline-stub) \
	  --embedder $(or $(EMBEDDER),local-hash)

# Paper figures from a crossover dataset (PDF with the [chart] extra, else SVG).
# CROSSOVER overrides the dataset; FORMAT overrides pdf.
paper-figs:
	python -m scripts.paper_figs --crossover $(or $(CROSSOVER),results/crossover_dataset.json) \
	  --out paper/figures --format $(or $(FORMAT),pdf)

# Build the paper PDF (needs a LaTeX toolchain: pdflatex + bibtex). Runs figures
# first so includegraphics resolves.
paper: paper-figs
	cd paper && pdflatex -interaction=nonstopmode main.tex && bibtex main && \
	  pdflatex -interaction=nonstopmode main.tex && pdflatex -interaction=nonstopmode main.tex

test:
	python -m pytest -q
