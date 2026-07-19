#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$repo_root/macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj"
scheme="GlyphsMCPInstaller"
python_bin="${PYTHON_BIN:-python3}"
xcodebuild_bin="${XCODEBUILD_BIN:-xcodebuild}"

cd "$repo_root"

echo "Checking release scripts…"
/bin/bash -n \
  scripts/build_installer_app.sh \
  scripts/notarize_installer_app.sh \
  scripts/make_installer_dmg.sh \
  scripts/publish_release_assets.sh \
  scripts/run_local_release_tests.sh \
  scripts/verify_release_artifacts.sh

echo "Checking tracked patch whitespace…"
git diff --check HEAD

echo "Running the complete Python test suite locally…"
"$python_bin" -m unittest discover -s src/glyphs-mcp/tests

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

echo "Local release tests passed. No artifacts were published."
