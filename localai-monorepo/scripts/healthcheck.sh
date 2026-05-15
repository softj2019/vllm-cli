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

HOST="${LOCALAI_HOST:-127.0.0.1}"
PORT="${LOCALAI_PORT:-8080}"
URL="http://$HOST:$PORT/v1/models"

curl -fsS "$URL" >/dev/null && echo "[OK] $URL" || {
  echo "[ERROR] healthcheck failed: $URL"
  exit 1
}
