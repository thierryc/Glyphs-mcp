#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Verify local Glyphs MCP release artifacts before publishing.

Usage:
  ./scripts/verify_release_artifacts.sh --tag vX.Y.Z [--write-checksums]

This requires Developer ID signatures, hardened runtime + secure timestamps,
valid stapled notarization tickets, Gatekeeper acceptance, aligned versions,
byte-identical versioned/latest DMGs, and a valid installed plug-in bundle seal.
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
python_bin="${PYTHON_BIN:-python3}"
tag=""
write_checksum_file="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag) tag="${2:-}"; shift 2 ;;
    --write-checksums) write_checksum_file="1"; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "error: unknown argument: $1" >&2; usage; exit 2 ;;
  esac
done

if [[ -z "$tag" ]]; then
  echo "error: --tag vX.Y.Z is required" >&2
  exit 2
fi

codesign_bin="${CODESIGN_BIN:-/usr/bin/codesign}"
spctl_bin="${SPCTL_BIN:-/usr/sbin/spctl}"
xcrun_bin="${XCRUN_BIN:-/usr/bin/xcrun}"
ditto_bin="${DITTO_BIN:-/usr/bin/ditto}"
expected_identity="${EXPECTED_CODESIGN_IDENTITY:-${CODESIGN_IDENTITY:-Developer ID Application: Thierry Charbonnel (N9U29A4T8J)}}"
expected_team="${EXPECTED_TEAM_ID:-N9U29A4T8J}"

product="${GLYPHS_MCP_APP_NAME:-Glyphs MCP}"
app="$repo_root/dist/installer-app/$product.app"
app_plist="$app/Contents/Info.plist"
payload_archive="$app/Contents/Resources/Payload.gmcparchive"
core_framework="$app/Contents/Frameworks/GlyphsMCPInstallerCore.framework"
updater_helper="$app/Contents/Resources/GlyphsMCPUpdater"
zip="$repo_root/dist/installer-app/$product.zip"

version="$("$python_bin" "$repo_root/scripts/release_security.py" metadata --repo-root "$repo_root" --tag "$tag" --app-plist "$app_plist")"
release_version="$("$python_bin" "$repo_root/scripts/desktop_release_identity.py" --field releaseVersion)"
release_channel="$("$python_bin" "$repo_root/scripts/desktop_release_identity.py" --field channel)"
dmg_versioned="$repo_root/dist/Glyphs-MCP-$release_version.dmg"
dmg_latest="$repo_root/dist/Glyphs-MCP-latest.dmg"
checksum_file="$repo_root/dist/SHA256SUMS"

required_paths=("$app" "$payload_archive" "$core_framework" "$updater_helper" "$zip" "$dmg_versioned")
if [[ "$release_channel" == "stable" ]]; then required_paths+=("$dmg_latest"); fi
for path in "${required_paths[@]}"; do
  if [[ ! -e "$path" ]]; then
    echo "error: missing release artifact: $path" >&2
    exit 1
  fi
done

verify_developer_id() {
  local target="$1"
  local deep="${2:-0}"
  if [[ "$deep" == "1" ]]; then
    "$codesign_bin" --verify --deep --strict --verbose=2 "$target"
  else
    "$codesign_bin" --verify --strict --verbose=2 "$target"
  fi
  local details
  details="$("$codesign_bin" -d --verbose=4 "$target" 2>&1)"
  if ! grep -Fq "Authority=$expected_identity" <<<"$details"; then
    echo "error: unexpected signing authority for $target" >&2
    exit 1
  fi
  if ! grep -Fq "TeamIdentifier=$expected_team" <<<"$details"; then
    echo "error: unexpected signing team for $target" >&2
    exit 1
  fi
}

verify_runtime_signature() {
  local target="$1"
  verify_developer_id "$target" "${2:-0}"
  local details
  details="$("$codesign_bin" -d --verbose=4 "$target" 2>&1)"
  if ! grep -Eq 'flags=.*\(runtime\)' <<<"$details"; then
    echo "error: hardened runtime is missing for $target" >&2
    exit 1
  fi
  if ! grep -Eq '^Timestamp=' <<<"$details"; then
    echo "error: secure timestamp is missing for $target" >&2
    exit 1
  fi
}

verify_payload_executables() {
  "$python_bin" "$repo_root/scripts/release_payload.py" verify "$1" --identity "$expected_identity" --installed
}

verify_runtime_signature "$app" 1
verify_runtime_signature "$core_framework" 0
verify_runtime_signature "$updater_helper" 0
verify_developer_id "$dmg_versioned" 0

"$xcrun_bin" stapler validate "$app"
"$xcrun_bin" stapler validate "$dmg_versioned"
"$spctl_bin" -a -vv -t exec "$app"
"$spctl_bin" -a -vv -t open --context context:primary-signature "$dmg_versioned"

if [[ "$release_channel" == "stable" ]] && ! cmp -s "$dmg_versioned" "$dmg_latest"; then
  echo "error: latest DMG is not byte-identical to the versioned DMG" >&2
  exit 1
fi

tmp_root="$(mktemp -d /tmp/gmcp-release-verify.XXXXXX)"
cleanup() { rm -rf "$tmp_root"; }
trap cleanup EXIT
"$ditto_bin" -x -k "$zip" "$tmp_root"
zipped_app="$tmp_root/$product.app"
if [[ ! -d "$zipped_app" ]]; then
  echo "error: release ZIP does not contain $product.app" >&2
  exit 1
fi
verify_runtime_signature "$zipped_app" 1
zipped_payload_archive="$zipped_app/Contents/Resources/Payload.gmcparchive"
if [[ ! -f "$zipped_payload_archive" ]]; then
  echo "error: installer ZIP is missing Payload.gmcparchive" >&2
  exit 1
fi
zipped_payload_extract="$tmp_root/extracted-signed-payload"
mkdir -p "$zipped_payload_extract"
/usr/bin/tar -xzf "$zipped_payload_archive" -C "$zipped_payload_extract"
zipped_payload_root="$zipped_payload_extract/Payload"
"$python_bin" "$repo_root/scripts/build_installer_payload.py" \
  --verify-root "$zipped_payload_root" \
  --release-version "$version"
verify_payload_executables "$zipped_payload_root"
zipped_core_framework="$zipped_app/Contents/Frameworks/GlyphsMCPInstallerCore.framework"
if [[ ! -d "$zipped_core_framework" ]]; then
  echo "error: installer ZIP is missing its core framework" >&2
  exit 1
fi
verify_runtime_signature "$zipped_core_framework" 0
zipped_updater_helper="$zipped_app/Contents/Resources/GlyphsMCPUpdater"
if [[ ! -f "$zipped_updater_helper" || -L "$zipped_updater_helper" ]]; then
  echo "error: installer ZIP is missing its regular updater helper" >&2
  exit 1
fi
verify_runtime_signature "$zipped_updater_helper" 0
if ! cmp -s "$updater_helper" "$zipped_updater_helper"; then
  echo "error: updater helper changed between the notarized app and release ZIP" >&2
  exit 1
fi
"$xcrun_bin" stapler validate "$zipped_app"
"$python_bin" "$repo_root/scripts/release_security.py" metadata \
  --repo-root "$repo_root" \
  --tag "$tag" \
  --app-plist "$zipped_app/Contents/Info.plist" >/dev/null

# release_payload.py verifies signature-preserving installed copies of Glyphs 3,
# the lean bridge, both companions and both complete private runtimes.

checksum_assets=("$dmg_versioned" "$zip")
if [[ "$release_channel" == "stable" ]]; then
  checksum_assets+=("$dmg_latest")
else
  checksum_assets=("$dmg_versioned" "$repo_root/dist/desktop-update/Glyphs-MCP-$release_version.zip" "$repo_root/dist/desktop-update/appcast.xml")
fi
checksum_stage="$tmp_root/release-assets"
mkdir -p "$checksum_stage"
flat_checksum_assets=()
for artifact in "${checksum_assets[@]}"; do
  staged_artifact="$checksum_stage/$(basename "$artifact")"
  if [[ -e "$staged_artifact" ]]; then
    echo "error: duplicate flattened release asset name: $(basename "$artifact")" >&2
    exit 1
  fi
  /bin/cp -p "$artifact" "$staged_artifact"
  flat_checksum_assets+=("$staged_artifact")
done
staged_checksum_file="$checksum_stage/SHA256SUMS"

if [[ "$write_checksum_file" == "1" ]]; then
  "$python_bin" "$repo_root/scripts/release_security.py" checksums \
    --base-dir "$checksum_stage" \
    --output "$staged_checksum_file" \
    "${flat_checksum_assets[@]}" >/dev/null
  /bin/cp -p "$staged_checksum_file" "$checksum_file"
fi

if [[ ! -f "$checksum_file" ]]; then
  echo "error: missing checksum manifest: $checksum_file" >&2
  echo "Run this verifier with --write-checksums after artifacts pass all other gates." >&2
  exit 1
fi
if [[ "$write_checksum_file" != "1" ]]; then
  /bin/cp -p "$checksum_file" "$staged_checksum_file"
fi
verify_checksum_args=()
for artifact in "${flat_checksum_assets[@]}"; do
  verify_checksum_args+=(--expect "$artifact")
done
"$python_bin" "$repo_root/scripts/release_security.py" verify-checksums \
  --base-dir "$checksum_stage" \
  "${verify_checksum_args[@]}" \
  "$staged_checksum_file" >/dev/null

echo "Release verification passed for $tag."
echo "Checksums: $checksum_file"
