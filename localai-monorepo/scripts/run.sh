#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

BIN="$ROOT_DIR/runtime/bin/local-ai"
PID_FILE="$ROOT_DIR/runtime/pids/localai.pid"
LOG_FILE="$ROOT_DIR/runtime/logs/localai.log"

mkdir -p "$ROOT_DIR/runtime/logs" "$ROOT_DIR/runtime/pids"

if [[ ! -x "$BIN" ]]; then
  echo "[ERROR] local-ai binary not found or not executable: $BIN"
  echo "        Place LocalAI binary at runtime/bin/local-ai and chmod +x it."
  exit 1
fi

if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
  echo "[INFO] LocalAI already running (pid=$(cat "$PID_FILE"))"
  exit 0
fi

HOST="${LOCALAI_HOST:-0.0.0.0}"
PORT="${LOCALAI_PORT:-8080}"
MODELS_DIR="${LOCALAI_MODELS_DIR:-./runtime/models}"
BACKENDS_DIR="${LOCALAI_BACKENDS_DIR:-./runtime/backends}"
CONFIG_DIR="${LOCALAI_CONFIG_DIR:-./configs/localai}"
THREADS="${LOCALAI_THREADS:-12}"
CTX="${LOCALAI_CONTEXT_SIZE:-8192}"
LOG_LEVEL="${LOCALAI_LOG_LEVEL:-info}"

nohup "$BIN" run \
  --address "$HOST:$PORT" \
  --models-path "$MODELS_DIR" \
  --backend-path "$BACKENDS_DIR" \
  --config-file "$CONFIG_DIR/models.yaml" \
  --threads "$THREADS" \
  --context-size "$CTX" \
  --log-level "$LOG_LEVEL" \
  > "$LOG_FILE" 2>&1 &

echo $! > "$PID_FILE"
echo "[OK] LocalAI started pid=$(cat "$PID_FILE") logs=$LOG_FILE"
