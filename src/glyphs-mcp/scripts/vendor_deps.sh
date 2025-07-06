#!/usr/bin/env bash
set -e
VENDOR=src/glyphs-mcp/build/site-packages
 # Destination inside the Glyphs plug‑in bundle
PLUGIN_PKG="src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Resources/site-packages"
rm -rf "$VENDOR"
python3 -m pip install --upgrade pip        # strong hint: use latest pip
python3 -m pip install \
  --target "$VENDOR" \
  --no-cache-dir \
  "fastmcp==2.10.*" \
  "uvicorn>=0.29" \
  starlette
# optional cleanup
find "$VENDOR" -name '__pycache__' -prune -exec rm -r {} +

# ── sync into the plug‑in bundle ────────────────────────────────
echo "Copying vendored packages into plug‑in bundle…"
rm -rf "$PLUGIN_PKG"
mkdir -p "$(dirname "$PLUGIN_PKG")"
cp -R "$VENDOR" "$PLUGIN_PKG"
echo "Done → $PLUGIN_PKG"