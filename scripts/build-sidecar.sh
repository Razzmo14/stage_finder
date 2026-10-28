#!/usr/bin/env bash
# Build the Python sidecar with PyInstaller and place it where Tauri
# expects externalBin binaries: src-tauri/binaries/<name>-<target-triple>.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_TRIPLE="${1:-$(rustc -vV | sed -n 's/^host: //p')}"

echo "==> Building sidecar (PyInstaller)"
(cd "$ROOT_DIR/backend" && uv run pyinstaller pyinstaller.spec --noconfirm)

mkdir -p "$ROOT_DIR/src-tauri/binaries"
cp "$ROOT_DIR/backend/dist/stage-finder-backend" \
   "$ROOT_DIR/src-tauri/binaries/stage-finder-backend-$TARGET_TRIPLE"
echo "==> Sidecar ready: src-tauri/binaries/stage-finder-backend-$TARGET_TRIPLE"
