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

if [[ "$configuration" != "Release" ]]; then
  echo "error: build_installer_app.sh only creates distributable Release builds" >&2
  echo "Use xcodebuild with CODE_SIGNING_ALLOWED=NO for local Debug validation." >&2
  exit 1
fi

if [[ "$identity" != "Developer ID Application: "* ]]; then
  echo "error: release identity must be a Developer ID Application certificate" >&2
  exit 1
fi

if ! /usr/bin/security find-identity -v -p codesigning | grep -Fq "\"$identity\""; then
  echo "error: signing identity is not available in the local keychain: $identity" >&2
  exit 1
fi

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

# Xcode/archive can leave Mach-O executables embedded in the payload with stale
# or ad-hoc signatures after export. This includes the main Glyphs plug-in and
# the pinned plug-in templates shipped by glyphs-mcp-development. Sign every
# nested Contents/MacOS executable before re-signing the outer app.
sign_nested_payload_executables() {
  local payload_root="$1"
  local signed_count=0

  if [[ ! -d "$payload_root" ]]; then
    echo "error: exported app payload not found at $payload_root" >&2
    exit 1
  fi

  while IFS= read -r -d '' candidate; do
    if /usr/bin/file -b "$candidate" | /usr/bin/grep -q 'Mach-O'; then
      echo "Re-signing payload executable: $candidate"
      /usr/bin/codesign --force --sign "$identity" --timestamp --options runtime "$candidate"
      signed_count=$((signed_count + 1))
    fi
  done < <(/usr/bin/find "$payload_root" -type f -path '*/Contents/MacOS/*' -print0)

  if [[ "$signed_count" -eq 0 ]]; then
    echo "error: no Mach-O payload executables were found under $payload_root" >&2
    exit 1
  fi
  echo "Re-signed $signed_count payload executable(s)."
}

payload_root="$out_dir/$scheme.app/Contents/Resources/Payload"
sign_nested_payload_executables "$payload_root"

echo "Re-signing exported app…"
/usr/bin/codesign --force --sign "$identity" --timestamp --options runtime "$out_dir/$scheme.app"

echo "Verifying exported app signature…"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$out_dir/$scheme.app"

signature_details="$(/usr/bin/codesign -d --verbose=4 "$out_dir/$scheme.app" 2>&1)"
if ! grep -Fq "Authority=$identity" <<<"$signature_details"; then
  echo "error: exported app is not signed by the requested Developer ID identity" >&2
  exit 1
fi
if ! grep -Eq 'flags=.*\(runtime\)' <<<"$signature_details"; then
  echo "error: exported app is missing hardened runtime" >&2
  exit 1
fi
if ! grep -Eq '^Timestamp=' <<<"$signature_details"; then
  echo "error: exported app is missing a secure timestamp" >&2
  exit 1
fi

echo "Wrote: $out_dir/$scheme.app"
