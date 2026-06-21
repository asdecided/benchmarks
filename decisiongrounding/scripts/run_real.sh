#!/usr/bin/env bash
#
# Real decision-grounding run. Everything is wired; this needs only credentials.
#
#   ANTHROPIC_API_KEY=...  ./scripts/run_real.sh            # headline compare (all arms, all real scenarios)
#   CROSSOVER=1 NS=10,50   ./scripts/run_real.sh            # also the adherence-vs-N curve over a real pool
#
# Required:  ANTHROPIC_API_KEY  (the held-constant answering model, claude-opus-4-8)
# Optional:  VOYAGE_API_KEY     (strong hosted embeddings for the naive_rag arm)
#            the `rac` CLI on PATH or RAC_BIN (the grounding layer under test)
#
# Knobs (env): ARMS, SCENARIOS, SEED, EMBEDDER, CROSSOVER, NS, POOL.
set -euo pipefail
cd "$(dirname "$0")/.."

ARMS="${ARMS:-context_dump,naive_rag,no_grounding,rac}"
SCENARIOS="${SCENARIOS:-scenarios_real}"
SEED="${SEED:-0}"
CROSSOVER="${CROSSOVER:-0}"
NS="${NS:-10,50}"
POOL="${POOL:-scenarios_real/peps_pool}"

# 1. Credentials. Anthropic is required; without it nothing real can run.
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ANTHROPIC_API_KEY is not set. Add it to the environment, then re-run." >&2
  exit 1
fi

# 2. Dependencies. The real answering model needs `anthropic`; install if absent.
python3 -c "import anthropic" 2>/dev/null || pip install -q "anthropic>=0.109"

# 3. Embedder for the naive_rag arm: prefer hosted Voyage (the strong, publishable
#    baseline); else a local sentence-transformers model; else the offline hash
#    (a WEAK baseline — fine for a smoke run, not for a published result).
if [ -z "${EMBEDDER:-}" ]; then
  if [ -n "${VOYAGE_API_KEY:-}" ]; then
    python3 -c "import voyageai" 2>/dev/null || pip install -q "voyageai>=0.4"
    EMBEDDER="voyage:voyage-4-large"
  elif python3 -c "import sentence_transformers" 2>/dev/null; then
    EMBEDDER="st:all-MiniLM-L6-v2"
  else
    EMBEDDER="local-hash"
    echo "WARNING: no VOYAGE_API_KEY and no sentence-transformers installed —" >&2
    echo "         naive_rag will use the offline local-hash embedder, a WEAK RAG" >&2
    echo "         baseline. For a publishable result: export VOYAGE_API_KEY=... " >&2
    echo "         (recommended) or: pip install -e '.[local-embeddings]'." >&2
  fi
fi

# 4. The rac arm is an external CLI. Ensure it is present, or drop it with a note.
if echo "$ARMS" | grep -qw rac && ! command -v "${RAC_BIN:-rac}" >/dev/null 2>&1; then
  if [ -d ../rac-core ]; then
    echo "rac CLI not on PATH; installing from ../rac-core ..." >&2
    pip install -q -e ../rac-core
  else
    echo "WARNING: rac arm requested but the rac CLI is not available; dropping it." >&2
    ARMS="$(printf '%s' "$ARMS" | tr ',' '\n' | grep -vx rac | paste -sd,)"
  fi
fi

# 5. Cost heads-up (every cell is one answering-model call).
n_scen="$(python3 -c "from scenarios.loader import load_scenarios; print(len(load_scenarios('$SCENARIOS')))")"
n_arms="$(printf '%s' "$ARMS" | awk -F, '{print NF}')"
echo "== config =="
echo "  arms=$ARMS"
echo "  answering=claude  embedder=$EMBEDDER  scenarios=$SCENARIOS ($n_scen)  seed=$SEED"
# Surface the resolved Anthropic endpoint — the anthropic SDK honours
# ANTHROPIC_BASE_URL, so a LiteLLM/proxy run is visible here. Probe it first with
# `python -m scripts.litellm_probe` (verifies structured outputs + the batch API).
if [ -n "${ANTHROPIC_BASE_URL:-}" ]; then
  echo "  endpoint=$ANTHROPIC_BASE_URL (via proxy — probe with scripts.litellm_probe)"
else
  echo "  endpoint=api.anthropic.com (direct)"
fi
echo "  compare cost ~= $n_arms arms x $n_scen scenarios = $((n_arms * n_scen)) answering-model calls"

# 6. Headline result: every arm on every real scenario at base corpus size.
#    Default (compare): synchronous, streams to results/run-*.partial.jsonl and
#    finalises to results/run-*.json; a transient error on one cell is recorded
#    and skipped, never losing the rest. BATCH=1: same comparison via the Batch
#    API at ~50% of standard price (asynchronous — submit, poll, then score).
HEADLINE_CMD="compare"
[ "${BATCH:-0}" = "1" ] && HEADLINE_CMD="batch"
python3 -m runner.cli "$HEADLINE_CMD" \
  --arms "$ARMS" --scenarios "$SCENARIOS" \
  --answering claude --embedder "$EMBEDDER" --seed "$SEED"

# 7. Optional adherence-vs-N crossover over a real distractor pool.
#    BATCH=1 routes the sweep's answering calls through the Batch API (~50% of
#    standard price, and it runs server-side so a client/container restart can't
#    lose it — strongly recommended for the full N sweep).
if [ "$CROSSOVER" = "1" ]; then
  [ -d "$POOL/corpus" ] || python3 -m ingest.peps pool build --out "$POOL"
  echo "== crossover (real distractors) =="
  echo "  cost ~= $n_arms arms x (discriminating scenarios) x |$NS| ns"
  CROSS_BATCH=""; [ "${BATCH:-0}" = "1" ] && CROSS_BATCH="--batch"
  python3 -m runner.cli demo \
    --scenarios "$SCENARIOS" --arms "$ARMS" \
    --distractors real --pool "$POOL" --ns "$NS" $CROSS_BATCH \
    --answering claude --embedder "$EMBEDDER" --seed "$SEED"
fi

echo
echo "Done. Reports in results/  (run-*.json + per-cell run-*.partial.jsonl)."
