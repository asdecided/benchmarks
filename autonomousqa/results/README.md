# Results

This directory is **append-only**: run reports are written once and never
mutated. Each `run-<UTC>-<label>.json` conforms to
`../schema/run_record.schema.json` per run and records, for every run, the
exact harness configuration (app, capability, agent and version, model, mode,
fidelity `n`) plus the raw evidence — the agent's stdout and exit code, the
metered token usage, and the wall clock.

Verdicts are never stored as trusted facts: `autonomousqa rescore` re-derives
them from the raw evidence, deterministically, with no agent, no model, and
no token spend. `autonomousqa report` renders `published/` from the same
records.

Runs whose `usage.estimated` is true came from the **scripted model** (the
harness's canned-flow stand-in). They are harness illustrations proving the
pipeline; they are never benchmark results. Published benchmark numbers come
from BYOK runs against real providers, with variance stated on the page.
