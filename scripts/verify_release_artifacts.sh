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

app="$repo_root/dist/installer-app/GlyphsMCPInstaller.app"
app_plist="$app/Contents/Info.plist"
payload_archive="$app/Contents/Resources/Payload.gmcparchive"
core_framework="$app/Contents/Frameworks/GlyphsMCPInstallerCore.framework"
updater_helper="$app/Contents/Resources/GlyphsMCPUpdater"
zip="$repo_root/dist/installer-app/GlyphsMCPInstaller.zip"

version="$(python3 "$repo_root/scripts/release_security.py" metadata --repo-root "$repo_root" --tag "$tag" --app-plist "$app_plist")"
dmg_versioned="$repo_root/dist/GlyphsMCPInstaller-$version.dmg"
dmg_latest="$repo_root/dist/GlyphsMCPInstaller.dmg"
checksum_file="$repo_root/dist/SHA256SUMS"

for path in "$app" "$payload_archive" "$core_framework" "$updater_helper" "$zip" "$dmg_versioned" "$dmg_latest"; do
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
  local root="$1"
  local verified_count=0
  local verified_bundle_count=0

  if [[ ! -d "$root" ]]; then
    echo "error: installer payload is missing: $root" >&2
    exit 1
  fi

  while IFS= read -r -d '' candidate; do
    if /usr/bin/file -b "$candidate" | /usr/bin/grep -q 'Mach-O'; then
      verify_runtime_signature "$candidate" 0
      verified_count=$((verified_count + 1))
    fi
  done < <(/usr/bin/find "$root" -type f -path '*/Contents/MacOS/*' -print0)

  if [[ "$verified_count" -eq 0 ]]; then
    echo "error: no Mach-O payload executables were found under $root" >&2
    exit 1
  fi
  while IFS= read -r -d '' bundle; do
    verify_runtime_signature "$bundle" 1
    verified_bundle_count=$((verified_bundle_count + 1))
  done < <(
    /usr/bin/find "$root" -depth -type d \
      \( -name '*.glyphsPlugin' -o -name '*.glyphsReporter' -o \
         -name '*.glyphsTool' -o -name '*.glyphsFilter' -o \
         -name '*.glyphsFileFormat' -o -name '*.glyphsPalette' \) \
      -print0
  )
  if [[ "$verified_bundle_count" -eq 0 ]]; then
    echo "error: no signed Glyphs code bundles were found under $root" >&2
    exit 1
  fi
  echo "Verified $verified_count payload executable(s) and $verified_bundle_count Glyphs code bundle(s) under $root."
}

verify_runtime_signature "$app" 1
verify_runtime_signature "$core_framework" 0
verify_runtime_signature "$updater_helper" 0
verify_developer_id "$dmg_versioned" 0

"$xcrun_bin" stapler validate "$app"
"$xcrun_bin" stapler validate "$dmg_versioned"
"$spctl_bin" -a -vv -t exec "$app"
"$spctl_bin" -a -vv -t open --context context:primary-signature "$dmg_versioned"

if ! cmp -s "$dmg_versioned" "$dmg_latest"; then
  echo "error: latest DMG is not byte-identical to the versioned DMG" >&2
  exit 1
fi

tmp_root="$(mktemp -d /tmp/gmcp-release-verify.XXXXXX)"
cleanup() { rm -rf "$tmp_root"; }
trap cleanup EXIT
"$ditto_bin" -x -k "$zip" "$tmp_root"
zipped_app="$tmp_root/GlyphsMCPInstaller.app"
if [[ ! -d "$zipped_app" ]]; then
  echo "error: installer ZIP does not contain GlyphsMCPInstaller.app" >&2
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
python3 "$repo_root/scripts/release_security.py" metadata \
  --repo-root "$repo_root" \
  --tag "$tag" \
  --app-plist "$zipped_app/Contents/Info.plist" >/dev/null

# Simulate the installer copy into an isolated Glyphs plug-in directory. The
# trusted nested executable must remain byte-identical and keep the same
# Developer ID CDHash after installation; no ad-hoc re-signing is permitted.
simulated_plugins="$tmp_root/simulated-install/Plugins"
mkdir -p "$simulated_plugins"
zipped_plugin="$zipped_payload_root/Glyphs MCP.glyphsPlugin"
installed_plugin="$simulated_plugins/Glyphs MCP.glyphsPlugin"
"$ditto_bin" "$zipped_plugin" "$installed_plugin"
installed_plugin_bin="$installed_plugin/Contents/MacOS/plugin"
verify_runtime_signature "$zipped_plugin" 1
verify_runtime_signature "$installed_plugin" 1
verify_runtime_signature "$installed_plugin_bin" 0
"$xcrun_bin" stapler validate "$zipped_plugin"
"$xcrun_bin" stapler validate "$installed_plugin"
if [[ ! -f "$zipped_plugin/Contents/CodeResources" || ! -f "$installed_plugin/Contents/CodeResources" ]]; then
  echo "error: the stapled plug-in notarization ticket did not survive installation" >&2
  exit 1
fi
if ! cmp -s "$zipped_plugin/Contents/MacOS/plugin" "$installed_plugin_bin"; then
  echo "error: installed plug-in executable changed during copy" >&2
  exit 1
fi
source_cdhash="$("$codesign_bin" -d --verbose=4 "$zipped_plugin/Contents/MacOS/plugin" 2>&1 | awk -F= '/^CDHash=/{value=$2} END{print value}')"
installed_cdhash="$("$codesign_bin" -d --verbose=4 "$installed_plugin_bin" 2>&1 | awk -F= '/^CDHash=/{value=$2} END{print value}')"
if [[ -z "$source_cdhash" || "$source_cdhash" != "$installed_cdhash" ]]; then
  echo "error: installed plug-in CDHash does not match the trusted payload" >&2
  exit 1
fi
echo "Verified signature-preserving simulated plug-in installation."

checksum_assets=("$dmg_versioned" "$dmg_latest" "$zip")

if [[ "$write_checksum_file" == "1" ]]; then
  python3 "$repo_root/scripts/release_security.py" checksums \
    --base-dir "$repo_root/dist" \
    --output "$checksum_file" \
    "${checksum_assets[@]}" >/dev/null
fi

if [[ ! -f "$checksum_file" ]]; then
  echo "error: missing checksum manifest: $checksum_file" >&2
  echo "Run this verifier with --write-checksums after artifacts pass all other gates." >&2
  exit 1
fi
verify_checksum_args=()
for artifact in "${checksum_assets[@]}"; do
  verify_checksum_args+=(--expect "$artifact")
done
python3 "$repo_root/scripts/release_security.py" verify-checksums \
  --base-dir "$repo_root/dist" \
  "${verify_checksum_args[@]}" \
  "$checksum_file" >/dev/null

echo "Release verification passed for $tag."
echo "Checksums: $checksum_file"
