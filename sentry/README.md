# SentryBench

SentryBench evaluates whether AsDecided's deterministic code enforcement
blocks known decision violations without blocking compliant or unrelated code.
It consumes the published `decided` CLI as an external process and never
imports Core.

This is not a retrieval benchmark. It scores enforcement correctness:

- `forbid_pattern`, `require_pattern`, and `forbid_import`
- SQL, Python, Rust, JavaScript/TypeScript, and unsupported-language failure
- full-tree certification and Git diff isolation
- invalid constraint fail-closed behaviour
- decision, rule, path, and line attribution in Sentry JSON
- SARIF source locations
- `decided sentry` / `decided gate --code` parity over their shared projection
- byte-identical JSON on repeated unchanged runs

The frozen set contains 80 contract cases, including 38 seeded violations,
multi-finding and ordering cases, diff-isolation edges, fail-closed behaviour,
and close-neighbour allow cases.

The committed fixture includes an eligible constrained decision, an explicitly
ineligible decision, and an intentionally unclassified decision. Coverage is
asserted but remains distinct from correctness.

## Run

```sh
python3 sentry/run.py
python3 sentry/run.py --json
python3 sentry/run.py --check
```

Set `RAC_BIN` to test a particular native executable:

```sh
RAC_BIN=/path/to/decided python3 sentry/run.py --check
```

## Supported-scale evidence

The scale profile deterministically generates a 5,000-decision corpus, then
checks clean and violating full-tree runs, a violating diff, composed-gate
parity, attribution, coverage accounting, and byte stability:

```sh
python3 sentry/run.py --scale
python3 sentry/run.py --scale --corpus-size 5000
```

The generated corpus is temporary: the repository does not carry 5,000
low-information fixture files. The profile reports elapsed time for each
surface, but correctness does not depend on a wall-clock threshold.

## Performance evidence

Timing is deliberately outside the scored metrics block:

```sh
python3 sentry/run.py --performance --iterations 30
```

This reports median, p95, minimum, and maximum engine time for a clean
full-tree profile and a violating diff profile. It does not gate CI until a
controlled runner profile and stable scale matrix are committed.

## Known boundary

`decided gate --code` does not yet expose Sentry's decision and rule
provenance. Parity therefore compares the public fields shared by both
surfaces: outcome, coverage, code, path, and line. The dedicated Sentry JSON
remains authoritative for decision and rule attribution.

## Gate

Every correctness metric is gated at `1.0` with zero tolerance. Baselines may
only be updated through the explicit, human-reviewed command:

```sh
python3 sentry/run.py --update-baseline
```

See `decisions/` and `requirements/` for the benchmark's governing contract.
