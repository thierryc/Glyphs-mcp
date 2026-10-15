#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/skills"
DESTINATION="$ROOT/plugins/glyphs-mcp/skills"
MANIFEST="$SOURCE/manifest.json"
MODE="sync"
SKILLS=()

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--check" ) ]]; then
  echo "Usage: $0 [--check]" >&2
  exit 2
fi
if [[ ${1:-} == "--check" ]]; then
  MODE="check"
fi

if [[ "$MODE" == "check" ]]; then
  python3 -B "$ROOT/scripts/sync_skill_catalog_metadata.py" --check
else
  python3 -B "$ROOT/scripts/sync_skill_catalog_metadata.py"
fi

if [[ ! -f "$ROOT/README.md" || ! -d "$SOURCE" || ! -f "$MANIFEST" ]]; then
  echo "Refusing to synchronize outside the Glyphs MCP repository." >&2
  exit 1
fi

while IFS= read -r skill; do
  SKILLS+=("$skill")
done < <(python3 -c 'import json,sys; data=json.load(open(sys.argv[1], encoding="utf-8")); print("\n".join(item["name"] for item in data["managedSkills"]))' "$MANIFEST")

if [[ ${#SKILLS[@]} -eq 0 ]]; then
  echo "The managed skill manifest is empty." >&2
  exit 1
fi

for skill in "${SKILLS[@]}"; do
  if [[ ! -f "$SOURCE/$skill/SKILL.md" ]]; then
    echo "Missing canonical skill: $skill" >&2
    exit 1
  fi
done

if [[ "$MODE" == "check" ]]; then
  if [[ ! -d "$DESTINATION" ]]; then
    echo "Missing packaged skill directory: $DESTINATION" >&2
    exit 1
  fi
  if ! cmp -s "$MANIFEST" "$DESTINATION/manifest.json"; then
    echo "The packaged managed skill manifest is out of sync." >&2
    echo "Run $0 to regenerate packaged skills from skills/." >&2
    exit 1
  fi
  for skill in "${SKILLS[@]}"; do
    if ! diff -qr -x '.DS_Store' -x '__pycache__' -x '*.pyc' -x '*.pyo' \
      "$SOURCE/$skill" "$DESTINATION/$skill"; then
      echo "The shared agent plugin skill '$skill' is out of sync." >&2
      echo "Run $0 to regenerate packaged skills from skills/." >&2
      exit 1
    fi
  done
  for packaged_path in "$DESTINATION"/*; do
    [[ -d "$packaged_path" ]] || continue
    packaged_name="$(basename "$packaged_path")"
    managed=false
    for skill in "${SKILLS[@]}"; do
      if [[ "$packaged_name" == "$skill" ]]; then
        managed=true
        break
      fi
    done
    if [[ "$managed" != true ]]; then
      echo "Unexpected packaged skill directory: $packaged_name" >&2
      exit 1
    fi
  done
  python3 - "$ROOT" <<'PY'
import json, sys
from pathlib import Path
root = Path(sys.argv[1]); sys.path.insert(0, str(root / 'scripts'))
from agent_package_identity import record
assert json.loads((root / 'plugins/glyphs-mcp/glyphs-mcp-agent.json').read_text()) == record(root), 'Agent package identity is stale; synchronize skills again'
PY
  echo "Verified ${#SKILLS[@]} synchronized Glyphs MCP skills in the shared agent plugin package."
  exit 0
fi

STAGING_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/glyphs-mcp-skills.XXXXXX")"
trap 'rm -rf "$STAGING_ROOT"' EXIT
STAGED_SKILLS="$STAGING_ROOT/skills"
mkdir -p "$STAGED_SKILLS"
cp "$MANIFEST" "$STAGED_SKILLS/manifest.json"

for skill in "${SKILLS[@]}"; do
  cp -R "$SOURCE/$skill" "$STAGED_SKILLS/$skill"
done

find "$STAGED_SKILLS" -name '.DS_Store' -delete
find "$STAGED_SKILLS" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$STAGED_SKILLS" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

rm -rf "$DESTINATION"
mv "$STAGED_SKILLS" "$DESTINATION"
python3 "$ROOT/scripts/agent_package_identity.py"
echo "Synchronized ${#SKILLS[@]} Glyphs MCP skills into the shared agent plugin package."
