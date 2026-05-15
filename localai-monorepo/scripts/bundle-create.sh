#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

STAMP="$(date +%Y%m%d-%H%M%S)"
OUT="artifacts/localai-offline-bundle-$STAMP.tar.gz"

if [[ ! -x runtime/bin/local-ai ]]; then
  echo "[ERROR] Missing runtime/bin/local-ai"
  exit 1
fi

mkdir -p artifacts

tar -czf "$OUT" \
  .env.example \
  README.md \
  scripts \
  configs \
  runtime/bin \
  runtime/models \
  runtime/backends

echo "[OK] Created bundle: $OUT"
