.PHONY: demo test compare pool crossover-real

# The one working comparison: two real arms, four worked scenarios, offline.
demo:
	python -m runner.cli demo

# Run a single named comparison, e.g. make compare ARMS=context_dump,naive_rag
compare:
	python -m runner.cli compare --arms $(ARMS)

# Build the real distractor pools from their pins (one network pass each:
# ~519 PEPs, ~371 RFCs). Pick the one matching your scenarios' domain.
pool:
	python -m ingest.peps pool build

rfc-pool:
	python -m ingest.rfcs pool build

# Rebuild + verify the real PEP and RFC scenario corpora from their pins.
corpora-verify:
	python -m ingest.peps verify  --out scenarios_real/peps_version_supersession
	python -m ingest.rfcs verify  --out scenarios_real/rfc_tls_version_supersession
	python -m ingest.rfcs verify  --out scenarios_real/rfc_rc4_prohibition

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
