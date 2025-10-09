#!/usr/bin/env bash
set -euo pipefail

# Install Python dependencies for Glyphs MCP using the Python that Glyphs installs
# via its Plugin Manager (GlyphsPythonPlugin). Packages are installed into the
# user-writable Scripts/site-packages so the plugin does not need to vendor deps.

here="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$here/../../.." && pwd)"
req_file="$repo_root/requirements.txt"

GLYPHS_BASE_DEFAULT="$HOME/Library/Application Support/Glyphs 3"
GLYPHS_BASE="${GLYPHS_BASE:-$GLYPHS_BASE_DEFAULT}"
PYTHON_BASE="$GLYPHS_BASE/Repositories/GlyphsPythonPlugin/Python.framework"
PIP_BIN="$PYTHON_BASE/Versions/Current/bin/pip3"
TARGET_DIR="$GLYPHS_BASE/Scripts/site-packages"

echo "Using GLYPHS_BASE: $GLYPHS_BASE"
echo "Expecting GlyphsPythonPlugin at: $PYTHON_BASE"

if [[ ! -x "$PIP_BIN" ]]; then
  echo "error: Glyphs Python not found."
  echo "- Open Glyphs → Settings → Addons and install Python (GlyphsPythonPlugin)."
  echo "- Then re-run this script."
  exit 1
fi

mkdir -p "$TARGET_DIR"

echo "Installing dependencies into: $TARGET_DIR"
"$PIP_BIN" install --upgrade pip
"$PIP_BIN" install --target="$TARGET_DIR" -r "$req_file"

echo "Done. Restart Glyphs if it is running."

