#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

REQUIRED=(
  "runtime/bin/local-ai"
  "scripts/run.sh"
  "scripts/stop.sh"
  "scripts/healthcheck.sh"
  "configs/localai/models.yaml"
)

for item in "${REQUIRED[@]}"; do
  if [[ ! -e "$item" ]]; then
    echo "[ERROR] Missing: $item"
    exit 1
  fi
done

if [[ ! -x runtime/bin/local-ai ]]; then
  echo "[ERROR] runtime/bin/local-ai is not executable"
  exit 1
fi

echo "[OK] bundle layout verified"
