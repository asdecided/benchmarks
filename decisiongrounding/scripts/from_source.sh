#!/usr/bin/env bash
#
# From-source launcher: set up a virtualenv, install the real backends, load your
# API keys, and run the benchmark. Use this right after cloning.
#
#   cp .env.example .env      # then put your keys in .env
#   ./scripts/from_source.sh                       # venv + install + headline compare
#   CROSSOVER=1 BATCH=1 ./scripts/from_source.sh   # + adherence-vs-N curve, batched
#
# Keys are read from .env (override with --env-file FILE) or from the environment
# if already exported. Nothing that reveals a secret is printed.
#
# Setup knobs (env):
#   ENV_FILE      key file to source        (default .env; or --env-file FILE)
#   VENV_DIR      virtualenv location       (default .venv)
#   VENV=0        use the current interpreter, do not create/activate a venv
#   EXTRAS        pip extras to install     (default real,schema,chart)
#   NO_INSTALL=1  skip venv + pip (just load keys and run)
#   PROBE=0       skip the proxy probe when ANTHROPIC_BASE_URL is set
#
# Run knobs are passed straight through to scripts/run_real.sh:
#   ARMS SCENARIOS SEED EMBEDDER CROSSOVER NS POOL BATCH  (+ ANTHROPIC_BASE_URL)
set -euo pipefail
cd "$(dirname "$0")/.."

ENV_FILE="${ENV_FILE:-.env}"
VENV_DIR="${VENV_DIR:-.venv}"
EXTRAS="${EXTRAS:-real,schema,chart}"

usage() { sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --env-file) ENV_FILE="${2:?--env-file needs a path}"; shift 2 ;;
    -h|--help)  usage; exit 0 ;;
    *) echo "unknown arg: $1  (run options are set via env; see --help)" >&2; exit 2 ;;
  esac
done

# 1. Load keys from the env file (shell-sourced KEY=value lines), unless they are
#    already exported. The file holds secrets, so it is gitignored.
case "$ENV_FILE" in */*) : ;; *) ENV_FILE="./$ENV_FILE" ;; esac
if [ -f "$ENV_FILE" ]; then
  echo "loading keys from $ENV_FILE"
  set -a; . "$ENV_FILE"; set +a
elif [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "no env file at '$ENV_FILE' and ANTHROPIC_API_KEY is not exported." >&2
  echo "  cp .env.example .env   # then add your keys (or export them, or pass --env-file)" >&2
  exit 1
fi

# 2. Virtualenv + editable install with the real backends (skip via NO_INSTALL=1).
if [ "${NO_INSTALL:-0}" != "1" ]; then
  if [ "${VENV:-1}" = "1" ] && [ -z "${VIRTUAL_ENV:-}" ]; then
    [ -d "$VENV_DIR" ] || { echo "creating virtualenv at $VENV_DIR"; python3 -m venv "$VENV_DIR"; }
    # shellcheck disable=SC1091
    . "$VENV_DIR/bin/activate"
  fi
  echo "installing decisiongrounding[$EXTRAS] (editable)…"
  python3 -m pip install -q --upgrade pip
  python3 -m pip install -q -e ".[$EXTRAS]"
fi

# 3. The answering key is mandatory; fail before any setup-heavy work spends time.
if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "ANTHROPIC_API_KEY is unset after loading '$ENV_FILE'. Add it and re-run." >&2
  exit 1
fi

# 4. If routed through a proxy, probe it before spending on the full run (the
#    benchmark needs native structured outputs + the Batch API to survive the hop).
if [ -n "${ANTHROPIC_BASE_URL:-}" ] && [ "${PROBE:-1}" = "1" ]; then
  echo "== ANTHROPIC_BASE_URL set — probing the proxy (PROBE=0 to skip) =="
  python3 -m scripts.litellm_probe || {
    echo "proxy probe failed — see README 'Through a proxy'. Fix it, or set PROBE=0." >&2
    exit 1
  }
fi

# 5. Hand off to the runner. It reads ARMS/SCENARIOS/SEED/EMBEDDER/CROSSOVER/NS/
#    POOL/BATCH from the environment, which we share here.
exec ./scripts/run_real.sh
