#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Build a Glyphs Plugin Manager-ready plugin bundle folder.

This copies ONLY tracked files from:
  src/glyphs-mcp/Glyphs MCP.glyphsPlugin
into:
  plugin-manager/Glyphs MCP.glyphsPlugin

Using tracked files avoids accidentally shipping local artifacts like:
  __pycache__, *.pyc, .DS_Store, __MACOSX, ._*, .venv, etc.

Usage:
  ./scripts/build_plugin_manager_bundle.sh
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

src_bundle="src/glyphs-mcp/Glyphs MCP.glyphsPlugin"
dst_bundle="plugin-manager/Glyphs MCP.glyphsPlugin"

if [[ ! -d "$src_bundle" ]]; then
  echo "error: source plugin bundle not found: $src_bundle" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "error: git not found in PATH" >&2
  exit 1
fi

echo "Building Plugin Manager bundle from tracked files:"
echo "  src: $src_bundle"
echo "  dst: $dst_bundle"

rm -rf "$dst_bundle"
mkdir -p "$(dirname "$dst_bundle")"
mkdir -p "$dst_bundle"

copied=0
while IFS= read -r -d '' file; do
  rel="${file#"$src_bundle/"}"
  if [[ "$rel" == "$file" ]]; then
    echo "error: unexpected path (not under $src_bundle): $file" >&2
    exit 1
  fi
  dest="$dst_bundle/$rel"
  mkdir -p "$(dirname "$dest")"
  cp -p "$file" "$dest"
  copied=$((copied + 1))
done < <(git ls-files -z "$src_bundle")

if [[ "$copied" -eq 0 ]]; then
  echo "error: no tracked files found under: $src_bundle" >&2
  exit 1
fi

# Ensure the plugin binary remains executable.
if [[ -f "$dst_bundle/Contents/MacOS/plugin" ]]; then
  chmod +x "$dst_bundle/Contents/MacOS/plugin" || true
fi

python3 - "$dst_bundle" <<'PY'
import os
import sys

root = sys.argv[1]

required = [
    os.path.join(root, "Contents", "Info.plist"),
    os.path.join(root, "Contents", "MacOS", "plugin"),
    os.path.join(root, "Contents", "Resources", "plugin.py"),
]

missing = [p for p in required if not os.path.exists(p)]
if missing:
    print("error: missing required files in built bundle:", file=sys.stderr)
    for p in missing:
        print(f"  - {p}", file=sys.stderr)
    raise SystemExit(1)

bad = []

def is_bad(rel_path: str) -> bool:
    parts = rel_path.split(os.sep)
    name = parts[-1]
    lower = rel_path.lower()

    if "__macosx" in parts:
        return True
    if name == ".DS_Store":
        return True
    if name.startswith("._") or f"{os.sep}._" in rel_path:
        return True
    if "__pycache__" in parts:
        return True
    if lower.endswith((".pyc", ".pyo")):
        return True
    if ".venv" in parts or "venv" in parts:
        return True
    if "site-packages" in parts:
        return True
    return False

for dirpath, dirnames, filenames in os.walk(root):
    # prune obvious dirs early
    dirnames[:] = [d for d in dirnames if d not in {"__pycache__", "__MACOSX", ".venv", "venv"}]

    for name in filenames:
        full = os.path.join(dirpath, name)
        rel = os.path.relpath(full, root)

        if os.path.islink(full):
            bad.append(f"{rel} (symlink)")
            continue
        if is_bad(rel):
            bad.append(rel)

if bad:
    print("error: bundle hygiene check failed; found disallowed entries:", file=sys.stderr)
    for entry in bad[:100]:
        print(f"  - {entry}", file=sys.stderr)
    if len(bad) > 100:
        print(f"  ... and {len(bad) - 100} more", file=sys.stderr)
    raise SystemExit(1)

print("Bundle hygiene check: OK")
PY

echo "Done. Copied $copied tracked files."
