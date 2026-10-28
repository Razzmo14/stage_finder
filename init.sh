#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

echo "==> Working directory: $PWD"

echo "==> Template verification"
python3 -m json.tool feature_list.json > /dev/null && echo "    feature_list.json: valid JSON"

# The code skeleton (feature skel-001) is not started yet: there is nothing
# to build or test. Once /backend, package.json and /src-tauri exist, this
# script runs the full baseline verification below.
if [ ! -d backend ] || [ ! -f package.json ] || [ ! -d src-tauri ]; then
  echo "==> Code skeleton not present yet (feature skel-001: not_started)."
  echo "==> Skipping toolchain verification."
  echo "==> Baseline verification passed (template-only)."
  exit 0
fi

echo "==> Prerequisites check"
fail=0
for cmd in node npm cargo uv python3.12; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "!! Missing prerequisite: $cmd"
    fail=1
  fi
done
if [ "$fail" = "1" ]; then
  echo "See docs/PRODUCT.md -> Technical Requirements."
  exit 1
fi

echo "==> Syncing Python backend (uv)"
uv sync --project backend

echo "==> Installing frontend dependencies (npm)"
npm install

echo "==> Running baseline verification"

echo "--> Backend: ruff"
(cd backend && uv run ruff check .)

echo "--> Backend: pytest"
(cd backend && uv run pytest)

echo "--> Frontend: build (tsc + vite)"
npm run build

if [ "${SKIP_CARGO_CHECK:-0}" != "1" ]; then
  echo "--> Rust core: cargo check (first run downloads crates; SKIP_CARGO_CHECK=1 to skip)"
  cargo check --manifest-path src-tauri/Cargo.toml
else
  echo "--> Rust core: cargo check skipped (SKIP_CARGO_CHECK=1)"
fi

if [ "${RUN_START_COMMAND:-0}" = "1" ]; then
  echo "==> Starting the app"
  exec npm run tauri dev
fi

echo "==> Baseline verification passed."
echo "Set RUN_START_COMMAND=1 if you want init.sh to launch the app directly."
