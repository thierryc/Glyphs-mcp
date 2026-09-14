#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$repo_root/macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj"
scheme="GlyphsMCPInstaller"
python_bin="${PYTHON_BIN:-python3}"
xcodebuild_bin="${XCODEBUILD_BIN:-xcodebuild}"

cd "$repo_root"

"$python_bin" scripts/prepare_desktop_dependencies.py

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

echo "Checking the lean package and shipped skills…"
release_version="$("$python_bin" scripts/desktop_release_identity.py --field version)"
installer_build="$("$python_bin" scripts/desktop_release_identity.py --field installerBuild)"
beta_number="$("$python_bin" scripts/desktop_release_identity.py --field betaNumber)"
"$python_bin" scripts/bump_version.py --dry-run --beta "$beta_number" "$release_version"
scripts/sync_codex_plugin_skills.sh --check
"$python_bin" scripts/check_lean_package.py
"$python_bin" scripts/build_installer_payload.py --output-root build/payload-check-a
"$python_bin" scripts/build_installer_payload.py --output-root build/payload-check-b
diff -qr build/payload-check-a build/payload-check-b
"$python_bin" scripts/qualify_private_runtime.py build/payload-check-a/Lean
(cd website && npm run build)

echo "Running the complete Python test suite locally…"
GLYPHS_MCP_FULL_PYTHON_MATRIX=1 PYTHON_BIN="$python_bin" scripts/run_python_tests.sh --pytest

derived_data="$(mktemp -d "${TMPDIR:-/tmp}/gmcp-release-tests.XXXXXX")"
cleanup() { rm -rf "$derived_data"; }
trap cleanup EXIT

echo "Running the complete macOS installer test suite locally…"
"$xcodebuild_bin" test \
  -project "$project" \
  -scheme "$scheme" \
  -destination 'platform=macOS' \
  -derivedDataPath "$derived_data" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO

echo "Building an unsigned Debug installer locally…"
"$xcodebuild_bin" build \
  -project "$project" \
  -scheme "$scheme" \
  -configuration Debug \
  -destination 'platform=macOS' \
  -derivedDataPath "$derived_data" \
  CODE_SIGNING_ALLOWED=NO \
  CODE_SIGNING_REQUIRED=NO

"$python_bin" scripts/verify_desktop_app.py "$derived_data/Build/Products/Debug/Glyphs MCP.app"

"$python_bin" scripts/release_security.py candidate --repo-root "$repo_root" --version "$release_version" --installer-build "$installer_build" --app-plist "$derived_data/Build/Products/Debug/Glyphs MCP.app/Contents/Info.plist" --payload-root build/payload-check-a

echo "Local release tests passed. No artifacts were published."
