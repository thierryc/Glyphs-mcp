#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/skills"
DESTINATION="$ROOT/plugins/glyphs-mcp/skills"
MODE="sync"
SKILLS=(
  glyphs
  glyphs-mcp-development
  glyphs-mcp-features
  glyphs-mcp-icon-font
  glyphs-mcp-italic-first-pass
  glyphs-mcp-kerning
  glyphs-mcp-litsquare-metadata
  glyphs-mcp-outlines-docs
  glyphs-mcp-release
  glyphs-mcp-spacing
)

if [[ $# -gt 1 || ( $# -eq 1 && "$1" != "--check" ) ]]; then
  echo "Usage: $0 [--check]" >&2
  exit 2
fi
if [[ ${1:-} == "--check" ]]; then
  MODE="check"
fi

if [[ ! -f "$ROOT/README.md" || ! -d "$SOURCE" ]]; then
  echo "Refusing to synchronize outside the Glyphs MCP repository." >&2
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
  echo "Verified ${#SKILLS[@]} synchronized Glyphs MCP skills in the shared agent plugin package."
  exit 0
fi

STAGING_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/glyphs-mcp-skills.XXXXXX")"
trap 'rm -rf "$STAGING_ROOT"' EXIT
STAGED_SKILLS="$STAGING_ROOT/skills"
mkdir -p "$STAGED_SKILLS"

for skill in "${SKILLS[@]}"; do
  cp -R "$SOURCE/$skill" "$STAGED_SKILLS/$skill"
done

find "$STAGED_SKILLS" -name '.DS_Store' -delete
find "$STAGED_SKILLS" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$STAGED_SKILLS" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete

rm -rf "$DESTINATION"
mv "$STAGED_SKILLS" "$DESTINATION"
echo "Synchronized ${#SKILLS[@]} Glyphs MCP skills into the shared agent plugin package."
