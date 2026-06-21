.PHONY: demo test compare pool rfc-pool crossover-real corpora-verify real-run real-crossover ui dashboard

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
# compare + the adherence-vs-N crossover over a real pool (set NS to taste):
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

# Verify the real scenario corpora reproduce from their pins (one per domain).
corpora-verify:
	python -m ingest.peps verify  --out scenarios_real/peps_version_supersession
	python -m ingest.rfcs verify  --out scenarios_real/rfc_tls_version_supersession
	python -m ingest.w3c  verify  --out scenarios_real/w3c_xml_edition_supersession

# Real adherence-vs-N curve over the real PEP pool. Offline by default
# (illustration); add ANSWERING=claude EMBEDDER=voyage:voyage-4-large + keys for
# the real result. NS keeps API spend tunable, e.g. NS=10,50.
crossover-real:
	python -m runner.cli demo --scenarios scenarios_real \
	  --arms context_dump,naive_rag,no_grounding,rac \
	  --distractors real --ns $(or $(NS),10,50,150,300) \
	  --answering $(or $(ANSWERING),offline-stub) \
	  --embedder $(or $(EMBEDDER),local-hash)

test:
	python -m pytest -q
