#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
runner="unittest"

usage() {
  cat <<'EOF'
Run the Glyphs MCP Python test suite in a preflighted development environment.

Usage:
  ./scripts/run_python_tests.sh [--unittest] [unittest arguments...]
  ./scripts/run_python_tests.sh --pytest [pytest arguments...]

Environment:
  PYTHON_BIN   Python 3.11-3.14 interpreter to use (default: python3)

Set up an isolated environment first when needed:
  python3.12 -m venv .venv
  .venv/bin/python -m pip install -r requirements-dev.txt
  PYTHON_BIN=.venv/bin/python ./scripts/run_python_tests.sh
EOF
}

case "${1:-}" in
  --pytest)
    runner="pytest"
    shift
    ;;
  --unittest)
    shift
    ;;
  -h|--help)
    usage
    exit 0
    ;;
esac

if [[ "$python_bin" == */* ]]; then
  if [[ ! -x "$python_bin" ]]; then
    echo "error: PYTHON_BIN is not executable: $python_bin" >&2
    exit 2
  fi
elif ! command -v "$python_bin" >/dev/null 2>&1; then
  echo "error: Python interpreter not found on PATH: $python_bin" >&2
  exit 2
fi

GLYPHS_MCP_TEST_RUNNER="$runner" GLYPHS_MCP_REPO_ROOT="$repo_root" "$python_bin" - <<'PY'
import importlib.util
import os
from pathlib import Path
import sys

if not ((3, 11) <= sys.version_info[:2] <= (3, 14)):
    print(
        "error: Glyphs MCP tests support Python 3.11-3.14; found {}.{}.".format(
            sys.version_info.major,
            sys.version_info.minor,
        ),
        file=sys.stderr,
    )
    raise SystemExit(2)

required = {
    "fastmcp": "fastmcp",
    "glyphsLib": "glyphsLib",
    "jsonschema": "jsonschema",
}
if os.environ["GLYPHS_MCP_TEST_RUNNER"] == "pytest":
    required["pytest"] = "pytest"

missing = [label for label, module in required.items() if importlib.util.find_spec(module) is None]
if missing:
    requirements = Path(os.environ["GLYPHS_MCP_REPO_ROOT"]) / "requirements-dev.txt"
    print(
        "error: {} is missing development test dependencies: {}".format(
            sys.executable,
            ", ".join(sorted(missing)),
        ),
        file=sys.stderr,
    )
    print(
        "hint: {} -m pip install -r {}".format(sys.executable, requirements),
        file=sys.stderr,
    )
    raise SystemExit(2)

print(
    "Python test environment: {} {}.{}.{} ({})".format(
        os.environ["GLYPHS_MCP_TEST_RUNNER"],
        sys.version_info.major,
        sys.version_info.minor,
        sys.version_info.micro,
        sys.executable,
    )
)
PY

cd "$repo_root"
if [[ "$runner" == "pytest" ]]; then
  # Do not let unrelated globally installed pytest plug-ins mutate the import
  # state used by FastMCP/Pydantic compatibility tests.
  if [[ "$#" -eq 0 ]]; then
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$python_bin" -m pytest src/glyphs-mcp/tests
  else
    PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "$python_bin" -m pytest "$@"
  fi
elif [[ "$#" -eq 0 ]]; then
  "$python_bin" -m unittest discover -s src/glyphs-mcp/tests
else
  "$python_bin" -m unittest "$@"
fi
