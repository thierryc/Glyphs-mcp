#!/usr/bin/env bash
set -euo pipefail

# Resolve important paths relative to this script, regardless of CWD
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"

VENDOR="$REPO_ROOT/src/glyphs-mcp/build/site-packages"
# Destination inside the Glyphs plug‑in bundle
PLUGIN_PKG="$REPO_ROOT/src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Resources/site-packages"
RUNTIME_REQS_FILE="$REPO_ROOT/requirements.runtime.txt"

rm -rf "$VENDOR"
python3 -m pip install --upgrade pip        # keep pip modern
python3 -m pip install \
  --target "$VENDOR" \
  --no-cache-dir \
  -r "$RUNTIME_REQS_FILE"

# optional cleanup
find "$VENDOR" -name '__pycache__' -prune -exec rm -r {} + || true

# ── sync into the plug‑in bundle ────────────────────────────────
echo "Copying vendored packages into plug‑in bundle…"
rm -rf "$PLUGIN_PKG"
mkdir -p "$(dirname "$PLUGIN_PKG")"
cp -R "$VENDOR" "$PLUGIN_PKG"
echo "Done → $PLUGIN_PKG" 
