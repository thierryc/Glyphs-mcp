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

# Xcode/archive can leave code embedded in the payload with stale or ad-hoc
# signatures after export. Remove those signatures before signing: replacing
# them in place with codesign --force can leave a universal Mach-O with a
# signature that passes the immediate local cache check but fails later.
# Sign every Mach-O loader first, then seal every Glyphs code bundle from the
# deepest bundle outward.
sign_nested_payload_code() {
  local payload_root="$1"
  local signed_executable_count=0
  local signed_bundle_count=0

  if [[ ! -d "$payload_root" ]]; then
    echo "error: exported app payload not found at $payload_root" >&2
    exit 1
  fi

  while IFS= read -r -d '' candidate; do
    if /usr/bin/file -b "$candidate" | /usr/bin/grep -q 'Mach-O'; then
      echo "Signing payload executable from a clean signature slot: $candidate"
      /usr/bin/codesign --remove-signature "$candidate" 2>/dev/null || true
      /usr/bin/codesign --sign "$identity" --timestamp --options runtime "$candidate"
      /usr/bin/codesign --verify --strict --verbose=2 "$candidate"
      signed_executable_count=$((signed_executable_count + 1))
    fi
  done < <(/usr/bin/find "$payload_root" -type f -path '*/Contents/MacOS/*' -print0)

  if [[ "$signed_executable_count" -eq 0 ]]; then
    echo "error: no Mach-O payload executables were found under $payload_root" >&2
    exit 1
  fi

  while IFS= read -r -d '' bundle; do
    echo "Sealing payload plug-in bundle: $bundle"
    /usr/bin/codesign --remove-signature "$bundle" 2>/dev/null || true
    /usr/bin/codesign --sign "$identity" --timestamp --options runtime "$bundle"
    /usr/bin/codesign --verify --deep --strict --verbose=2 "$bundle"
    signed_bundle_count=$((signed_bundle_count + 1))
  done < <(
    /usr/bin/find "$payload_root" -depth -type d \
      \( -name '*.glyphsPlugin' -o -name '*.glyphsReporter' -o \
         -name '*.glyphsTool' -o -name '*.glyphsFilter' -o \
         -name '*.glyphsFileFormat' -o -name '*.glyphsPalette' \) \
      -print0
  )

  if [[ "$signed_bundle_count" -eq 0 ]]; then
    echo "error: no payload Glyphs code bundles were found under $payload_root" >&2
    exit 1
  fi
  echo "Signed $signed_executable_count payload executable(s) and sealed $signed_bundle_count Glyphs code bundle(s)."
}

payload_root="$out_dir/$scheme.app/Contents/Resources/Payload"
sign_nested_payload_code "$payload_root"

# Archive the fully signed payload so the installer app seals one immutable
# compressed-tar resource and the installer can independently verify the
# extracted plug-in before copying it.
payload_archive="$out_dir/$scheme.app/Contents/Resources/Payload.gmcparchive"
payload_check="$(mktemp -d /tmp/gmcp-signed-payload-check.XXXXXX)"
cleanup_payload_check() { rm -rf "$payload_check"; }
trap cleanup_payload_check EXIT
rm -f "$payload_archive"
COPYFILE_DISABLE=1 /usr/bin/tar -czf "$payload_archive" -C "$(dirname "$payload_root")" "$(basename "$payload_root")"
/usr/bin/tar -xzf "$payload_archive" -C "$payload_check"
checked_payload="$payload_check/Payload"
checked_plugin="$checked_payload/Glyphs MCP.glyphsPlugin"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$checked_plugin"
while IFS= read -r -d '' candidate; do
  if /usr/bin/file -b "$candidate" | /usr/bin/grep -q 'Mach-O'; then
    /usr/bin/codesign --verify --strict --verbose=2 "$candidate"
  fi
done < <(/usr/bin/find "$checked_payload" -type f -path '*/Contents/MacOS/*' -print0)
payload_archive_sha256_before_signing="$(/usr/bin/shasum -a 256 "$payload_archive" | /usr/bin/awk '{print $1}')"
rm -rf "$payload_root"
echo "Embedded immutable signed payload archive: $payload_archive"

echo "Signing exported app from a clean signature slot…"
/usr/bin/codesign --remove-signature "$out_dir/$scheme.app" 2>/dev/null || true
/usr/bin/codesign --sign "$identity" --timestamp --options runtime "$out_dir/$scheme.app"

# codesign can satisfy an immediate verification from the signing cache. Give
# securityd time to evict that entry so this gate exercises durable validation,
# which is what a user's Mac and Apple's notarization service will see.
sleep 15

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

# The outer app signature must not alter the archived plug-in. Verify both the
# container bytes and every nested code signature again after signing the app.
# This is the release regression gate for the Gatekeeper failure reported when
# Glyphs loads an installed plug-in.
payload_archive_sha256_after_signing="$(/usr/bin/shasum -a 256 "$payload_archive" | /usr/bin/awk '{print $1}')"
if [[ "$payload_archive_sha256_before_signing" != "$payload_archive_sha256_after_signing" ]]; then
  echo "error: signing the installer app changed the signed payload archive" >&2
  exit 1
fi
rm -rf "$payload_check"
mkdir -p "$payload_check"
/usr/bin/tar -xzf "$payload_archive" -C "$payload_check"
checked_payload="$payload_check/Payload"
checked_plugin="$checked_payload/Glyphs MCP.glyphsPlugin"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$checked_plugin"
while IFS= read -r -d '' candidate; do
  if /usr/bin/file -b "$candidate" | /usr/bin/grep -q 'Mach-O'; then
    /usr/bin/codesign --verify --strict --verbose=2 "$candidate"
  fi
done < <(/usr/bin/find "$checked_payload" -type f -path '*/Contents/MacOS/*' -print0)

echo "Wrote: $out_dir/$scheme.app"
