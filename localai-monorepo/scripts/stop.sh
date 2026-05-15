#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="$ROOT_DIR/runtime/pids/localai.pid"

if [[ ! -f "$PID_FILE" ]]; then
  echo "[INFO] No pid file."
  exit 0
fi

PID="$(cat "$PID_FILE")"
if kill -0 "$PID" 2>/dev/null; then
  kill "$PID"
  echo "[OK] Stopped LocalAI pid=$PID"
else
  echo "[WARN] Process not running pid=$PID"
fi

rm -f "$PID_FILE"
