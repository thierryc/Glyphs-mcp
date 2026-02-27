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

read_plist_key() {
  local plist_path="$1"
  local key="$2"

  if [[ -x /usr/libexec/PlistBuddy ]]; then
    /usr/libexec/PlistBuddy -c "Print :$key" "$plist_path" 2>/dev/null || true
    return 0
  fi

  python3 - "$plist_path" "$key" <<'PY'
import plistlib
import sys
from pathlib import Path

plist_path = Path(sys.argv[1])
key = sys.argv[2]
try:
    with plist_path.open("rb") as f:
        data = plistlib.load(f)
    v = data.get(key, "")
except Exception:
    v = ""
print(v if v is not None else "")
PY
}

set_plist_key() {
  local plist_path="$1"
  local key="$2"
  local value="$3"

  if [[ -x /usr/libexec/PlistBuddy ]]; then
    /usr/libexec/PlistBuddy -c "Set :$key $value" "$plist_path" 2>/dev/null \
      || /usr/libexec/PlistBuddy -c "Add :$key string $value" "$plist_path"
    return 0
  fi

  python3 - "$plist_path" "$key" "$value" <<'PY'
import plistlib
import sys
from pathlib import Path

plist_path = Path(sys.argv[1])
key = sys.argv[2]
value = sys.argv[3]

with plist_path.open("rb") as f:
    data = plistlib.load(f)
data[key] = value
with plist_path.open("wb") as f:
    plistlib.dump(data, f, fmt=plistlib.FMT_XML, sort_keys=False)
PY
}

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

src_info_plist="$src_bundle/Contents/Info.plist"
dst_info_plist="$dst_bundle/Contents/Info.plist"

if [[ ! -f "$src_info_plist" ]]; then
  echo "error: source Info.plist not found: $src_info_plist" >&2
  exit 1
fi

# Cache clean (enforced): remove common local artifacts from the SOURCE bundle
# so dev installs (symlink) and ad-hoc copies don't accidentally use stale bytecode.
#
# The build itself only copies tracked files, but cleaning here prevents confusing
# mismatches (e.g. older .pyc being loaded when running a symlinked plugin).
find "$src_bundle" -name ".DS_Store" -print0 2>/dev/null | xargs -0 rm -f 2>/dev/null || true
find "$src_bundle" -name "__pycache__" -type d -print0 2>/dev/null | xargs -0 rm -rf 2>/dev/null || true
find "$src_bundle" -name "*.pyc" -print0 2>/dev/null | xargs -0 rm -f 2>/dev/null || true
find "$src_bundle" -name "*.pyo" -print0 2>/dev/null | xargs -0 rm -f 2>/dev/null || true
find "$src_bundle" -name "__MACOSX" -type d -print0 2>/dev/null | xargs -0 rm -rf 2>/dev/null || true
find "$src_bundle" -name "._*" -print0 2>/dev/null | xargs -0 rm -f 2>/dev/null || true

src_version="$(read_plist_key "$src_info_plist" "CFBundleShortVersionString")"
src_build="$(read_plist_key "$src_info_plist" "CFBundleVersion")"
if [[ -z "$src_version" || -z "$src_build" ]]; then
  echo "error: could not read version keys from $src_info_plist" >&2
  exit 1
fi
if [[ "$src_version" != "$src_build" ]]; then
  echo "error: source Info.plist mismatch: CFBundleShortVersionString=$src_version CFBundleVersion=$src_build" >&2
  exit 1
fi
echo "  version: $src_version"

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

# Ensure the destination bundle version matches the source (guard against stale
# outputs if the script ever changes to do partial/incremental copies).
dst_version="$(read_plist_key "$dst_info_plist" "CFBundleShortVersionString")"
dst_build="$(read_plist_key "$dst_info_plist" "CFBundleVersion")"
if [[ "$dst_version" != "$src_version" || "$dst_build" != "$src_version" ]]; then
  echo "warning: destination Info.plist version mismatch; rewriting to $src_version" >&2
  set_plist_key "$dst_info_plist" "CFBundleShortVersionString" "$src_version"
  set_plist_key "$dst_info_plist" "CFBundleVersion" "$src_version"
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
