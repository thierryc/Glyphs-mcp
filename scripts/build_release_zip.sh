#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Build a clean release ZIP for the Glyphs MCP plugin bundle.

This uses `git ls-files` so the ZIP only contains tracked files and never
accidentally ships local artifacts like __pycache__, .venv, __MACOSX, etc.

Usage:
  ./scripts/build_release_zip.sh [--version X.Y.Z] [--output PATH] [--no-check]

Options:
  --version X.Y.Z   Version label used in the output filename (default: Info.plist CFBundleShortVersionString)
  --output PATH     Output ZIP path (default: dist/Glyphs MCP.glyphsPlugin-v<VERSION>.zip)
  --no-check        Skip the post-build hygiene scan
  -h, --help        Show this help
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

plugin_dir="src/glyphs-mcp/Glyphs MCP.glyphsPlugin"
info_plist="$plugin_dir/Contents/Info.plist"

version=""
output=""
do_check="1"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)
      version="${2:-}"; shift 2 ;;
    --output)
      output="${2:-}"; shift 2 ;;
    --no-check)
      do_check="0"; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2 ;;
  esac
done

if [[ ! -d "$plugin_dir" ]]; then
  echo "error: plugin directory not found: $plugin_dir" >&2
  exit 1
fi

if [[ -z "$version" ]]; then
  if [[ -f "$info_plist" ]] && [[ -x /usr/libexec/PlistBuddy ]]; then
    version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$info_plist" 2>/dev/null || true)"
  fi
fi

if [[ -z "$version" ]]; then
  version="dev"
fi

if [[ -z "$output" ]]; then
  mkdir -p dist
  output="dist/Glyphs MCP.glyphsPlugin-v${version}.zip"
fi

echo "Building release ZIP from tracked files:"
echo "  plugin:  $plugin_dir"
echo "  output:  $output"

python3 - "$plugin_dir" "$output" <<'PY'
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

plugin_dir = Path(sys.argv[1]).resolve()
output = Path(sys.argv[2]).resolve()

prefix = "Glyphs MCP.glyphsPlugin/"

if not plugin_dir.is_dir():
    raise SystemExit(f"error: plugin directory not found: {plugin_dir}")

try:
    result = subprocess.run(
        ["git", "ls-files", "-z", str(plugin_dir)],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
except subprocess.CalledProcessError as exc:
    raise SystemExit(f"error: git ls-files failed: {exc.stderr.decode('utf-8', errors='replace')}")

tracked = [p for p in result.stdout.split(b"\x00") if p]
if not tracked:
    raise SystemExit(f"error: no tracked files found under: {plugin_dir}")

output.parent.mkdir(parents=True, exist_ok=True)
if output.exists():
    output.unlink()

with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
    for raw in tracked:
        rel = Path(raw.decode("utf-8", errors="strict"))
        abs_path = (Path.cwd() / rel).resolve()
        if not abs_path.is_file():
            continue

        arcname = prefix + abs_path.relative_to(plugin_dir).as_posix()

        info = zipfile.ZipInfo(arcname)
        st = abs_path.stat()
        info.date_time = tuple(__import__("time").localtime(st.st_mtime)[:6])
        # Preserve executable bits (important for Contents/MacOS/plugin).
        mode = stat.S_IMODE(st.st_mode)
        info.external_attr = (mode & 0xFFFF) << 16

        with abs_path.open("rb") as f:
            data = f.read()
        zf.writestr(info, data)

print(f"Wrote: {output}")
PY

if [[ "$do_check" == "1" ]]; then
  python3 - "$output" <<'PY'
import sys
import zipfile

zip_path = sys.argv[1]

bad = []
with zipfile.ZipFile(zip_path) as zf:
    for name in zf.namelist():
        lower = name.lower()
        if name.startswith("__MACOSX/"):
            bad.append(name)
            continue
        if lower.endswith(".ds_store"):
            bad.append(name)
            continue
        if "/__pycache__/" in name:
            bad.append(name)
            continue
        if lower.endswith((".pyc", ".pyo")):
            bad.append(name)
            continue
        if "/.venv/" in name or lower.startswith(".venv/"):
            bad.append(name)
            continue
        # AppleDouble metadata files
        if "/._" in name or name.startswith("._"):
            bad.append(name)
            continue

if bad:
    print("error: ZIP hygiene check failed; found disallowed entries:", file=sys.stderr)
    for entry in bad[:50]:
        print(f"  - {entry}", file=sys.stderr)
    if len(bad) > 50:
        print(f"  ... and {len(bad) - 50} more", file=sys.stderr)
    raise SystemExit(1)

print("ZIP hygiene check: OK")
PY
fi

echo "Done."
