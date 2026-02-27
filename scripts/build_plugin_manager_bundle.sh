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
  ./scripts/build_plugin_manager_bundle.sh [--vendor|--vendor-from-installed] [--vendor-source PATH] [--allow-missing-targets]

Options:
  --vendor                 Vendor Python deps into the Plugin Manager bundle under:
                           Contents/Resources/vendor/<py>-<arch>/site-packages
                           (FastMCP requires compiled wheels like pydantic_core.)
  --vendor-from-installed  Copy an existing Glyphs Scripts/site-packages into the vendor
                           folder (offline-friendly). Only copies when ABI/arch matches.
  --vendor-source PATH     Site-packages directory to copy when using --vendor-from-installed
                           (default: ~/Library/Application Support/Glyphs 3/Scripts/site-packages).
  --allow-missing-targets  Skip targets whose Python interpreter is missing instead
                           of failing the build.
EOF
}

vendor_mode="0"
allow_missing_targets="0"
vendor_from_installed="0"
vendor_source=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --vendor)
      vendor_mode="1"; shift ;;
    --vendor-from-installed)
      vendor_mode="1"; vendor_from_installed="1"; shift ;;
    --vendor-source)
      vendor_source="${2:-}"; shift 2 ;;
    --allow-missing-targets)
      allow_missing_targets="1"; shift ;;
    -h|--help)
      usage; exit 0 ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 2 ;;
  esac
done

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

src_bundle="src/glyphs-mcp/Glyphs MCP.glyphsPlugin"
dst_bundle="plugin-manager/Glyphs MCP.glyphsPlugin"
requirements_file="requirements.txt"

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

if [[ "$vendor_mode" == "1" ]] && [[ ! -f "$requirements_file" ]]; then
  echo "error: requirements file not found: $requirements_file" >&2
  exit 1
fi

echo "Building Plugin Manager bundle from tracked files:"
echo "  src: $src_bundle"
echo "  dst: $dst_bundle"
if [[ "$vendor_mode" == "1" ]]; then
  echo "  vendoring: enabled"
  if [[ "$vendor_from_installed" == "1" ]]; then
    echo "  vendoring: from installed site-packages"
  fi
fi

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

VENDOR_MODE="$vendor_mode" python3 - "$dst_bundle" <<'PY'
import os
import sys

root = sys.argv[1]
vendor_mode = os.environ.get("VENDOR_MODE", "0") == "1"

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
        if vendor_mode:
            # Allow vendored deps only under Contents/Resources/vendor/**/site-packages.
            return "vendor" not in parts
        # Strict mode: disallow any site-packages in the Plugin Manager bundle.
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

if [[ "$vendor_mode" == "1" ]]; then
  glyphs_py_bin="$HOME/Library/Application Support/Glyphs 3/Repositories/GlyphsPythonPlugin/Python.framework/Versions/Current/bin"
  py311_arm64="$glyphs_py_bin/python3.11"
  py311_x64="$glyphs_py_bin/python3.11-intel64"

  py312_bin="$(command -v python3.12 2>/dev/null || true)"

  vendor_root="$dst_bundle/Contents/Resources/vendor"
  rm -rf "$vendor_root"
  mkdir -p "$vendor_root"

  if [[ -z "$vendor_source" ]]; then
    vendor_source="$HOME/Library/Application Support/Glyphs 3/Scripts/site-packages"
  fi

  target_names=( "py311-arm64" "py311-x86_64" "py312-arm64" "py312-x86_64" )

  # Resolve interpreter commands per target. For py312-x86_64 use a universal2 python
  # and run it under Rosetta when on Apple Silicon.
  cmd_for_target() {
    local target="$1"
    case "$target" in
      py311-arm64) echo "$py311_arm64" ;;
      py311-x86_64) echo "$py311_x64" ;;
      py312-arm64) echo "$py312_bin" ;;
      py312-x86_64) echo "arch -x86_64 $py312_bin" ;;
      *) echo "" ;;
    esac
  }

  run_py() {
    local target="$1"; shift
    case "$target" in
      py311-arm64) "$py311_arm64" "$@" ;;
      py311-x86_64) "$py311_x64" "$@" ;;
      py312-arm64) "$py312_bin" "$@" ;;
      py312-x86_64) arch -x86_64 "$py312_bin" "$@" ;;
      *) return 127 ;;
    esac
  }

  py_ok() {
    local target="$1"
    run_py "$target" -c 'import sys; print(sys.version.split()[0])' >/dev/null 2>&1
  }

  missing=()
  for t in "${target_names[@]}"; do
    cmd="$(cmd_for_target "$t")"
    if [[ -z "$cmd" ]]; then
      missing+=("$t (no interpreter configured)")
      continue
    fi
    if ! py_ok "$t"; then
      missing+=("$t ($cmd)")
    fi
  done

  if [[ "${#missing[@]}" -gt 0 && "$allow_missing_targets" != "1" ]]; then
    echo "error: missing Python interpreters for vendoring:" >&2
    for m in "${missing[@]}"; do
      echo "  - $m" >&2
    done
    echo "hint: ensure GlyphsPythonPlugin is installed for py311 targets, and install" >&2
    echo "      python.org Python 3.12 (universal2) for py312 targets," >&2
    echo "      or re-run with --allow-missing-targets to skip missing targets." >&2
    exit 1
  fi

  build_one_target() {
    local target="$1"
    local out_dir="$vendor_root/$target/site-packages"

    echo "Vendoring deps for $target"
    echo "  python: $(cmd_for_target "$target")"
    echo "  output: $out_dir"

    rm -rf "$vendor_root/$target"

    if [[ "$vendor_from_installed" == "1" ]]; then
      if [[ ! -d "$vendor_source" ]]; then
        echo "error: vendor source site-packages not found: $vendor_source" >&2
        exit 1
      fi

      # Safety: only copy into matching ABI targets. We detect by presence of the
      # pydantic_core binary wheel filename and its architecture.
      pyd_core="$(ls "$vendor_source"/pydantic_core/_pydantic_core*.so 2>/dev/null | head -n 1 || true)"
      if [[ -z "$pyd_core" ]]; then
        echo "error: vendor source does not contain pydantic_core binary; cannot vendor FastMCP deps from it." >&2
        exit 1
      fi

      abi_ok="0"
      case "$target" in
        py311-arm64)
          if [[ "$pyd_core" == *"cpython-311"* ]]; then
            if file "$pyd_core" | grep -q "arm64"; then
              abi_ok="1"
            elif file "$pyd_core" | grep -q "universal binary"; then
              abi_ok="1"
            fi
          fi
          ;;
        py311-x86_64)
          if [[ "$pyd_core" == *"cpython-311"* ]] && file "$pyd_core" | grep -q "x86_64"; then
            abi_ok="1"
          fi
          ;;
        py312-arm64|py312-x86_64)
          # Source folder is typically tied to one Python minor version; do not guess.
          abi_ok="0"
          ;;
      esac

      if [[ "$abi_ok" != "1" ]]; then
        echo "Skipping $target: vendor source ($vendor_source) does not match this ABI/arch." >&2
        return 0
      fi

      mkdir -p "$out_dir"
      if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete \
          --exclude "__pycache__/" \
          --exclude ".DS_Store" \
          --exclude "__MACOSX/" \
          --exclude "._*" \
          --exclude "*.pyc" \
          --exclude "*.pyo" \
          "$vendor_source/" "$out_dir/"
      else
        # Fallback: copy everything (best effort).
        cp -R "$vendor_source/." "$out_dir/"
      fi
    else
      mkdir -p "$out_dir"
      PYTHONDONTWRITEBYTECODE=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
        run_py "$target" -m pip install \
          --no-compile \
          --no-cache-dir \
          --only-binary=:all: \
          --target "$out_dir" \
          -r "$requirements_file"
    fi

    # Clean Python caches inside vendored site-packages.
    find "$out_dir" -name "__pycache__" -type d -print0 2>/dev/null | xargs -0 rm -rf 2>/dev/null || true
    find "$out_dir" -name "*.pyc" -print0 2>/dev/null | xargs -0 rm -f 2>/dev/null || true
    find "$out_dir" -name "*.pyo" -print0 2>/dev/null | xargs -0 rm -f 2>/dev/null || true
    find "$out_dir" -name ".DS_Store" -print0 2>/dev/null | xargs -0 rm -f 2>/dev/null || true
    find "$out_dir" -name "__MACOSX" -type d -print0 2>/dev/null | xargs -0 rm -rf 2>/dev/null || true
    find "$out_dir" -name "._*" -print0 2>/dev/null | xargs -0 rm -f 2>/dev/null || true

    # Verify core imports for this target.
    PYTHONPATH="$out_dir" run_py "$target" -c "import fastmcp, mcp, pydantic_core; print('OK')" >/dev/null

    py_version="$(run_py "$target" -c 'import sys; print(sys.version.split()[0])')"
    py_machine="$(run_py "$target" -c 'import platform; print(platform.machine())')"
    py_display="$(cmd_for_target "$target")"

    # Record a minimal manifest entry.
    python3 - "$vendor_root/manifest.json" "$target" "$py_display" "$py_version" "$py_machine" "$out_dir" <<'PY'
import json
import sys
import time
from pathlib import Path

manifest_path = Path(sys.argv[1])
target = sys.argv[2]
py_display = sys.argv[3]
py_version = sys.argv[4]
py_machine = sys.argv[5]
site_packages = Path(sys.argv[6])

def dist_list(site_dir: Path):
    out = []
    for meta in sorted(site_dir.glob("*.dist-info/METADATA")):
        name = None
        version = None
        try:
            for line in meta.read_text(encoding="utf-8", errors="replace").splitlines():
                if line.startswith("Name: "):
                    name = line.split("Name: ", 1)[1].strip()
                elif line.startswith("Version: "):
                    version = line.split("Version: ", 1)[1].strip()
                if name and version:
                    break
        except Exception:
            continue
        if name and version:
            out.append({"name": name, "version": version})
    return out

data = {}
if manifest_path.exists():
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}

data.setdefault("generatedAt", int(time.time()))
targets = data.setdefault("targets", {})

targets[target] = {
    "python": py_display,
    "pythonVersion": py_version,
    "machine": py_machine,
    "sitePackages": str(site_packages),
    "packages": dist_list(site_packages),
}

manifest_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
PY
  }

  for t in "${target_names[@]}"; do
    cmd="$(cmd_for_target "$t")"
    if [[ -z "$cmd" ]]; then
      continue
    fi
    # Skip missing targets when allowed.
    if ! py_ok "$t"; then
      continue
    fi
    build_one_target "$t"
  done

  # Patch ONLY the plugin-manager bundle's plugin.py to prefer vendored deps.
  dst_plugin_py="$dst_bundle/Contents/Resources/plugin.py"
  if [[ ! -f "$dst_plugin_py" ]]; then
    echo "error: destination plugin.py not found: $dst_plugin_py" >&2
    exit 1
  fi

  python3 - "$dst_plugin_py" <<'PY'
import sys
from pathlib import Path

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

marker_start = "# --- Glyphs MCP Vendor Deps (Plugin Manager build) ---"
marker_end = "# --- End Glyphs MCP Vendor Deps ---"

block = f"""{marker_start}
def _maybe_prefer_vendored_site_packages() -> None:
    try:
        import platform

        py_tag = f\"py{{sys.version_info.major}}{{sys.version_info.minor}}\"
        machine = (platform.machine() or \"\").lower()
        if machine == \"aarch64\":
            machine = \"arm64\"
        vendor_root = Path(__file__).resolve().parent / \"vendor\"
        candidate = vendor_root / f\"{{py_tag}}-{{machine}}\" / \"site-packages\"
        if not candidate.is_dir():
            return
        cand = str(candidate)
        # De-dupe and prefer vendored deps.
        sys.path[:] = [p for p in sys.path if p != cand]
        sys.path.insert(0, cand)
    except Exception:
        pass

_maybe_prefer_vendored_site_packages()
{marker_end}
"""

needle = "_ensure_user_site_packages_on_path()"
if needle not in text:
    raise SystemExit("error: could not find _ensure_user_site_packages_on_path() call in plugin.py")

if marker_start in text:
    # If the source ever gets this block, avoid double insertion.
    path.write_text(text, encoding="utf-8")
    raise SystemExit(0)

lines = text.splitlines(True)
out = []
inserted = False
for line in lines:
    if (not inserted) and line.strip() == needle:
        out.append(block)
        inserted = True
    out.append(line)

if not inserted:
    raise SystemExit("error: failed to insert vendor block into plugin.py")

path.write_text("".join(out), encoding="utf-8")
PY

  echo "Vendoring complete."

  # Re-run hygiene check now that vendored site-packages exists.
  VENDOR_MODE="1" python3 - "$dst_bundle" <<'PY'
import os
import sys

root = sys.argv[1]

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
        # Allow vendored deps only under Contents/Resources/vendor/**/site-packages.
        return "vendor" not in parts
    return False

for dirpath, dirnames, filenames in os.walk(root):
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
    print("error: bundle hygiene check failed after vendoring; found disallowed entries:", file=sys.stderr)
    for entry in bad[:100]:
        print(f"  - {entry}", file=sys.stderr)
    if len(bad) > 100:
        print(f"  ... and {len(bad) - 100} more", file=sys.stderr)
    raise SystemExit(1)

print("Bundle hygiene check (vendor mode): OK")
PY
fi

echo "Done. Copied $copied tracked files."
