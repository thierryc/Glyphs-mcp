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
PYTHON_BIN="$PYTHON_BASE/Versions/Current/bin/python3"
TARGET_DIR="$GLYPHS_BASE/Scripts/site-packages"
PROBE="$repo_root/src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Resources/runtime_probe.py"

echo "Using GLYPHS_BASE: $GLYPHS_BASE"
echo "Expecting GlyphsPythonPlugin at: $PYTHON_BASE"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "error: Glyphs Python not found."
  echo "- Open Glyphs → Settings → Addons and install Python (GlyphsPythonPlugin)."
  echo "- Then re-run this script."
  exit 1
fi

preflight_json="$("$PYTHON_BIN" "$PROBE" --mode preinstall --site-packages "$TARGET_DIR")"
install_mode="$("$PYTHON_BIN" -c 'import json,sys; print(json.loads(sys.argv[1])["pathPlan"]["installMode"])' "$preflight_json")"
primary_root="$("$PYTHON_BIN" -c 'import json,sys; print(json.loads(sys.argv[1])["pathPlan"]["primaryRoot"])' "$preflight_json")"
ordered_roots="$("$PYTHON_BIN" -c 'import json,os,sys; print(os.pathsep.join(json.loads(sys.argv[1])["pathPlan"]["orderedRoots"]))' "$preflight_json")"

destination=(--user)
if [[ "$install_mode" == "target" ]]; then
  mkdir -p "$primary_root"
  destination=(--target "$primary_root")
fi

echo "Installing dependencies into: $primary_root"
PYTHONPATH="$ordered_roots${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON_BIN" -m pip install \
  --upgrade --upgrade-strategy only-if-needed \
  --disable-pip-version-check --no-input --progress-bar off --timeout 30 --retries 2 \
  --no-compile --only-binary=:all: "${destination[@]}" -r "$req_file"
postflight_json="$("$PYTHON_BIN" "$PROBE" --mode postinstall --site-packages "$TARGET_DIR")"
"$PYTHON_BIN" -c 'import json,sys; before=json.loads(sys.argv[1])["pathPlan"]; after=json.loads(sys.argv[2])["pathPlan"]; raise SystemExit(0 if before == after else "runtime path plan drift")' "$preflight_json" "$postflight_json"

echo "Done. Restart Glyphs if it is running."
