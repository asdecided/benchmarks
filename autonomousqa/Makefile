# Developer entry points. The core spine is stdlib-only Python; the reference
# agent runs from the pinned node workspace (make workspace).

PY ?= python3

.PHONY: help workspace apps smoke fixtures test report clean

help:
	@echo "workspace  install the pinned node workspace (reference agent + playwright)"
	@echo "apps       list the frozen sample apps and their capabilities"
	@echo "smoke      one scripted capability end to end + deterministic re-score"
	@echo "fixtures   verify every scripted flow across all apps (needs workspace + rac)"
	@echo "test       run the offline pytest battery"
	@echo "report     render results/published from recorded results (RESULTS=...)"

workspace:
	cd workspace && npm ci && npx playwright install chromium

apps:
	$(PY) -m runner.cli apps

smoke:
	$(PY) -m runner.cli smoke

fixtures:
	$(PY) -m runner.cli run --app api-ledger --mode scripted --label fixtures --strict
	$(PY) -m runner.cli run --app browser-notes --mode scripted --label fixtures --strict
	$(PY) -m runner.cli run --app cli-tally --mode scripted --label fixtures --strict
	$(PY) -m runner.cli run --app ext-wordbadge --mode scripted --label fixtures --strict

test:
	$(PY) -m pytest -q

report:
	$(PY) -m runner.cli report $(RESULTS) --label $(LABEL)

clean:
	rm -rf runs workspace/generated workspace/test-results workspace/tests workspace/.proofkeeper
