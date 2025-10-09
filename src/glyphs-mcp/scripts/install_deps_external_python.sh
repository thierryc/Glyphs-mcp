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

# Pick a Python interpreter
if [[ -n "$PY_ARG" ]]; then
  PYTHON="$PY_ARG"
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

echo "Installing dependencies into user site for: $PYTHON"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install --user -r "$req_file"

echo "Done. Restart Glyphs if it is running."
