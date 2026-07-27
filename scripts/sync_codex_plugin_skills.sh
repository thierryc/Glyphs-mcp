#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE="$ROOT/skills"
DESTINATION="$ROOT/plugins/glyphs-mcp/skills"
SKILLS=(
  glyphs
  glyphs-mcp-development
  glyphs-mcp-features
  glyphs-mcp-icon-font
  glyphs-mcp-italic-first-pass
  glyphs-mcp-kerning
  glyphs-mcp-outlines-docs
  glyphs-mcp-spacing
)

if [[ ! -f "$ROOT/README.md" || ! -d "$SOURCE" ]]; then
  echo "Refusing to synchronize outside the Glyphs MCP repository." >&2
  exit 1
fi

rm -rf "$DESTINATION"
mkdir -p "$DESTINATION"

for skill in "${SKILLS[@]}"; do
  if [[ ! -f "$SOURCE/$skill/SKILL.md" ]]; then
    echo "Missing canonical skill: $skill" >&2
    exit 1
  fi
  cp -R "$SOURCE/$skill" "$DESTINATION/$skill"
done

find "$DESTINATION" -name '.DS_Store' -delete
find "$DESTINATION" -type d -name '__pycache__' -prune -exec rm -rf {} +
find "$DESTINATION" -type f \( -name '*.pyc' -o -name '*.pyo' \) -delete
echo "Synchronized ${#SKILLS[@]} Glyphs MCP skills."
