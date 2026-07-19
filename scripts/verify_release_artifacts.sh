#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Verify local Glyphs MCP release artifacts before publishing.

Usage:
  ./scripts/verify_release_artifacts.sh --tag vX.Y.Z [--include-plugin-zip] [--write-checksums]

This requires Developer ID signatures, hardened runtime + secure timestamps,
valid stapled notarization tickets, Gatekeeper acceptance, aligned versions,
and byte-identical versioned/latest DMGs.
EOF
}

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
tag=""
include_plugin_zip="0"
write_checksum_file="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --tag) tag="${2:-}"; shift 2 ;;
    --include-plugin-zip) include_plugin_zip="1"; shift ;;
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
payload_bin="$app/Contents/Resources/Payload/Glyphs MCP.glyphsPlugin/Contents/MacOS/plugin"
core_framework="$app/Contents/Frameworks/GlyphsMCPInstallerCore.framework"
zip="$repo_root/dist/installer-app/GlyphsMCPInstaller.zip"

version="$(python3 "$repo_root/scripts/release_security.py" metadata --repo-root "$repo_root" --tag "$tag" --app-plist "$app_plist")"
dmg_versioned="$repo_root/dist/GlyphsMCPInstaller-$version.dmg"
dmg_latest="$repo_root/dist/GlyphsMCPInstaller.dmg"
checksum_file="$repo_root/dist/SHA256SUMS"

for path in "$app" "$payload_bin" "$core_framework" "$zip" "$dmg_versioned" "$dmg_latest"; do
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

verify_runtime_signature "$app" 1
verify_runtime_signature "$payload_bin" 0
verify_runtime_signature "$core_framework" 0
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
zipped_payload_bin="$zipped_app/Contents/Resources/Payload/Glyphs MCP.glyphsPlugin/Contents/MacOS/plugin"
if [[ ! -f "$zipped_payload_bin" ]]; then
  echo "error: installer ZIP is missing its plug-in payload executable" >&2
  exit 1
fi
verify_runtime_signature "$zipped_payload_bin" 0
zipped_core_framework="$zipped_app/Contents/Frameworks/GlyphsMCPInstallerCore.framework"
if [[ ! -d "$zipped_core_framework" ]]; then
  echo "error: installer ZIP is missing its core framework" >&2
  exit 1
fi
verify_runtime_signature "$zipped_core_framework" 0
"$xcrun_bin" stapler validate "$zipped_app"
python3 "$repo_root/scripts/release_security.py" metadata \
  --repo-root "$repo_root" \
  --tag "$tag" \
  --app-plist "$zipped_app/Contents/Info.plist" >/dev/null

checksum_assets=("$dmg_versioned" "$dmg_latest" "$zip")
if [[ "$include_plugin_zip" == "1" ]]; then
  plugin_zip="$repo_root/dist/Glyphs MCP.glyphsPlugin-v$version.zip"
  if [[ ! -f "$plugin_zip" ]]; then
    echo "error: missing plug-in ZIP: $plugin_zip" >&2
    exit 1
  fi
  checksum_assets+=("$plugin_zip")
fi

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
