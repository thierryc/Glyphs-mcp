#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$repo_root/macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj"
scheme="GlyphsMCPInstaller"

identity="${CODESIGN_IDENTITY:-Developer ID Application: Thierry Charbonnel (N9U29A4T8J)}"
configuration="${CONFIGURATION:-Release}"
derived_data="${DERIVED_DATA_PATH:-/tmp/gmcp-installer-deriveddata}"

out_dir="$repo_root/dist/installer-app"
archive_path="$out_dir/$scheme.xcarchive"

mkdir -p "$out_dir"

echo "Building archive:"
echo "  project: $project"
echo "  scheme:  $scheme"
echo "  config:  $configuration"
echo "  sign:    $identity"
echo "  dd:      $derived_data"

xcodebuild \
  -project "$project" \
  -scheme "$scheme" \
  -configuration "$configuration" \
  -destination 'generic/platform=macOS' \
  -archivePath "$archive_path" \
  -derivedDataPath "$derived_data" \
  CODE_SIGN_STYLE=Manual \
  CODE_SIGN_IDENTITY="$identity" \
  PROVISIONING_PROFILE_SPECIFIER="" \
  archive

echo "Exporting .app…"

app_path="$archive_path/Products/Applications/$scheme.app"
if [[ ! -d "$app_path" ]]; then
  echo "error: app not found at $app_path" >&2
  exit 1
fi

rm -rf "$out_dir/$scheme.app"
/usr/bin/ditto "$app_path" "$out_dir/$scheme.app"

# Xcode/archive can leave the embedded payload executable with a stale signature
# after export. Re-sign the payload executable in the exported app, then re-sign
# the outer app bundle so the final distributable verifies cleanly.
payload_bin="$out_dir/$scheme.app/Contents/Resources/Payload/Glyphs MCP.glyphsPlugin/Contents/MacOS/plugin"
if [[ -f "$payload_bin" ]]; then
  echo "Re-signing exported payload executable…"
  /usr/bin/codesign --force --sign "$identity" --timestamp --options runtime "$payload_bin"
else
  echo "warn: payload executable not found at $payload_bin" >&2
fi

echo "Re-signing exported app…"
/usr/bin/codesign --force --sign "$identity" --timestamp --options runtime "$out_dir/$scheme.app"

echo "Verifying exported app signature…"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$out_dir/$scheme.app"

echo "Wrote: $out_dir/$scheme.app"
