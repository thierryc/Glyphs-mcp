#!/usr/bin/env bash
set -euo pipefail

# Install Python dependencies for Glyphs MCP using an external Python
# (e.g., python.org installer or Homebrew). Dependencies are installed into the
# selected Python's own site-packages (user scope) — nothing is written into
# Glyphs' Scripts directory.

usage() {
  cat <<EOF
Usage: $(basename "$0") [--python /path/to/python]

Installs requirements into the specified Python's user site (pip --user).

Options:
  --python PATH   Path to Python interpreter to use (default: auto-detect 3.12)
EOF
}

PY_ARG=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --python)
      PY_ARG="$2"; shift 2 ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1"; usage; exit 1 ;;
  esac
done

here="$(cd "$(dirname "$0")" && pwd)"
repo_root="$(cd "$here/../../.." && pwd)"
req_file="$repo_root/requirements.txt"
glyphs_version="${GLYPHS_MCP_GLYPHS_VERSION:-4}"
glyphs_site="$HOME/Library/Application Support/Glyphs $glyphs_version/Scripts/site-packages"
probe="$repo_root/src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Resources/runtime_probe.py"

# Pick a Python interpreter
if [[ -n "$PY_ARG" ]]; then
  PYTHON="$PY_ARG"
elif [[ -x "/Library/Frameworks/Python.framework/Versions/Current/bin/python3.12" ]]; then
  PYTHON="/Library/Frameworks/Python.framework/Versions/Current/bin/python3.12"
elif [[ -x "/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12" ]]; then
  PYTHON="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON="$(command -v python3.12)"
else
  PYTHON="$(command -v python3)"
  echo "warning: python3.12 not found, falling back to: $PYTHON"
fi

echo "Using Python: $PYTHON"
"$PYTHON" -c 'import sys; print(sys.version)' || { echo "error: failed to run $PYTHON"; exit 1; }

preflight_json="$("$PYTHON" "$probe" --mode preinstall --site-packages "$glyphs_site")"
install_mode="$("$PYTHON" -c 'import json,sys; print(json.loads(sys.argv[1])["pathPlan"]["installMode"])' "$preflight_json")"
primary_root="$("$PYTHON" -c 'import json,sys; print(json.loads(sys.argv[1])["pathPlan"]["primaryRoot"])' "$preflight_json")"
ordered_roots="$("$PYTHON" -c 'import json,os,sys; print(os.pathsep.join(json.loads(sys.argv[1])["pathPlan"]["orderedRoots"]))' "$preflight_json")"
destination=(--user)
if [[ "$install_mode" == "target" ]]; then
  mkdir -p "$primary_root"
  destination=(--target "$primary_root")
fi

echo "Installing dependencies into: $primary_root"
PYTHONPATH="$ordered_roots${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" -m pip install --upgrade --upgrade-strategy only-if-needed \
  --disable-pip-version-check --no-input --progress-bar off --timeout 30 --retries 2 \
  --no-compile --only-binary=:all: "${destination[@]}" -r "$req_file"
postflight_json="$(PYTHONPATH="$ordered_roots${PYTHONPATH:+:$PYTHONPATH}" "$PYTHON" "$probe" --mode postinstall --site-packages "$glyphs_site")"
"$PYTHON" -c 'import json,sys; before=json.loads(sys.argv[1])["pathPlan"]; after=json.loads(sys.argv[2])["pathPlan"]; raise SystemExit(0 if before == after else "runtime path plan drift")' "$preflight_json" "$postflight_json"

echo "Done. Restart Glyphs if it is running."
