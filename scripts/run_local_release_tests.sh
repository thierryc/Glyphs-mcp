#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$repo_root/macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj"
scheme="GlyphsMCPInstaller"
python_bin="${PYTHON_BIN:-python3}"
xcodebuild_bin="${XCODEBUILD_BIN:-xcodebuild}"
skill_validator="${SKILL_VALIDATOR:-${CODEX_HOME:-$HOME/.codex}/skills/.system/skill-creator/scripts/quick_validate.py}"

cd "$repo_root"

# Build phases run from Xcode-owned working directories. Resolve configured
# tools once so every child process receives the same executable regardless of
# its current directory.
if [[ "$python_bin" == */* ]]; then
  python_bin="$(cd "$(dirname "$python_bin")" && pwd)/$(basename "$python_bin")"
else
  python_bin="$(command -v "$python_bin")"
fi

echo "Checking exact release dependency pins…"
"$python_bin" scripts/check_release_dependencies.py \
  --requirements requirements-dev.txt \
  fontmake uharfbuzz

echo "Checking committed Glyphs 4 native-export parity evidence…"
"$python_bin" scripts/validate_glyphs4_native_parity.py

release_version="$("$python_bin" -c 'import sys; sys.path.insert(0, "src/glyphs-mcp-v2"); from glyphs_mcp_v2.versions import SERVER_VERSION; print(SERVER_VERSION)')"
installer_build="$("$python_bin" -c 'import importlib.util, pathlib; p=pathlib.Path("scripts/release_security.py"); s=importlib.util.spec_from_file_location("release_security", p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); print(next(iter(m.read_xcode_versions(pathlib.Path("macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj"))[1])))')"

echo "Checking release scripts…"
/bin/bash -n \
  scripts/build_installer_app.sh \
  scripts/notarize_installer_app.sh \
  scripts/make_installer_dmg.sh \
  scripts/publish_release_assets.sh \
  scripts/run_python_tests.sh \
  scripts/run_local_release_tests.sh \
  scripts/verify_release_artifacts.sh

echo "Checking tracked patch whitespace…"
git diff --check HEAD

echo "Checking target-aware version migration without changing the worktree…"
"$python_bin" scripts/bump_version.py \
  --dry-run \
  --installer-build "$installer_build" \
  "$release_version"

echo "Checking pinned Glyphs format knowledge dependencies offline…"
"$python_bin" scripts/release_security.py knowledge --repo-root "$repo_root"
"$python_bin" scripts/audit_canonical_schema_v6.py --repo-root "$repo_root"
if [[ "${GLYPHS_MCP_FULL_NETWORK:-0}" == "1" ]]; then
  echo "Comparing pinned Glyphs format dependencies with upstream heads…"
  "$python_bin" scripts/release_security.py knowledge \
    --repo-root "$repo_root" \
    --check-upstream
  "$python_bin" scripts/audit_canonical_schema_v6.py \
    --repo-root "$repo_root" \
    --check-upstream
fi

echo "Running the complete Python test suite locally…"
GLYPHS_MCP_FULL_PYTHON_MATRIX=1 PYTHON_BIN="$python_bin" scripts/run_python_tests.sh

derived_data="$(mktemp -d "${TMPDIR:-/tmp}/gmcp-release-tests.XXXXXX")"
cleanup() { rm -rf "$derived_data"; }
trap cleanup EXIT

payload_first="$derived_data/payload-first/Payload"
payload_second="$derived_data/payload-second/Payload"

echo "Building the deterministic dual-target installer payload twice…"
"$python_bin" scripts/build_installer_payload.py \
  --output-root "$payload_first" \
  --allow-outside-worktree
"$python_bin" scripts/build_installer_payload.py \
  --output-root "$payload_second" \
  --allow-outside-worktree
diff -qr "$payload_first" "$payload_second"
"$python_bin" scripts/build_installer_payload.py \
  --verify-root "$payload_first" \
  --release-version "$release_version"

echo "Checking canonical and packaged skill synchronization…"
scripts/sync_codex_plugin_skills.sh --check
"$python_bin" scripts/render_v2_command_reference.py --check
if [[ ! -f "$skill_validator" ]]; then
  echo "Missing skill validator: $skill_validator" >&2
  echo "Set SKILL_VALIDATOR to the skill-creator quick_validate.py path." >&2
  exit 1
fi
for skill_path in skills/* plugins/glyphs-mcp/skills/*; do
  [[ -f "$skill_path/SKILL.md" ]] || continue
  "$python_bin" "$skill_validator" "$skill_path"
done

echo "Building the documentation website…"
(cd website && npm run build)

echo "Running the complete macOS installer test suite locally…"
PYTHON_BIN="$python_bin" "$xcodebuild_bin" test \
  -project "$project" \
  -scheme "$scheme" \
  -destination 'platform=macOS' \
  -derivedDataPath "$derived_data" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO

echo "Building an unsigned Debug installer locally…"
PYTHON_BIN="$python_bin" "$xcodebuild_bin" build \
  -project "$project" \
  -scheme "$scheme" \
  -configuration Debug \
  -destination 'platform=macOS' \
  -derivedDataPath "$derived_data" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO

echo "Validating the unsigned asymmetric release candidate…"
"$python_bin" scripts/release_security.py candidate \
  --repo-root "$repo_root" \
  --version "$release_version" \
  --installer-build "$installer_build" \
  --payload-root "$payload_first" \
  --app-plist "$derived_data/Build/Products/Debug/GlyphsMCPInstaller.app/Contents/Info.plist"

echo "Local release tests passed. No artifacts were published."
