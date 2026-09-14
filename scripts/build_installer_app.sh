#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
project="$repo_root/macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj"
scheme="GlyphsMCPInstaller"
product="${GLYPHS_MCP_APP_NAME:-Glyphs MCP}"

identity="${CODESIGN_IDENTITY:-Developer ID Application: Thierry Charbonnel (N9U29A4T8J)}"
configuration="${CONFIGURATION:-Release}"
python_bin="${PYTHON_BIN:-python3}"
derived_data_root="${DERIVED_DATA_PATH:-$repo_root/build/xcode-runs}"

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

"$python_bin" "$repo_root/scripts/prepare_desktop_dependencies.py"
mkdir -p "$out_dir"
mkdir -p "$derived_data_root"
derived_data="$(mktemp -d "$derived_data_root/release.XXXXXX")"
cleanup_build() { rm -rf "$derived_data"; }
trap cleanup_build EXIT

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
  ARCHS="arm64 x86_64" ONLY_ACTIVE_ARCH=NO \
  CODE_SIGN_STYLE=Manual \
  CODE_SIGN_IDENTITY="$identity" \
  PROVISIONING_PROFILE_SPECIFIER="" \
  archive

echo "Exporting .app…"

app_path="$archive_path/Products/Applications/$product.app"
if [[ ! -d "$app_path" ]]; then
  echo "error: app not found at $app_path" >&2
  exit 1
fi

"$python_bin" "$repo_root/scripts/verify_desktop_app.py" "$app_path"

rm -rf "$out_dir/$product.app"
/usr/bin/ditto "$app_path" "$out_dir/$product.app"

updater_helper="$out_dir/$product.app/Contents/Resources/GlyphsMCPUpdater"
if [[ ! -f "$updater_helper" || -L "$updater_helper" ]]; then
  echo "error: exported app is missing the regular GlyphsMCPUpdater helper" >&2
  exit 1
fi
echo "Signing embedded updater helper from a clean signature slot…"
/usr/bin/codesign --remove-signature "$updater_helper" 2>/dev/null || true
/usr/bin/codesign --sign "$identity" --timestamp --options runtime "$updater_helper"
/usr/bin/codesign --verify --strict --verbose=2 "$updater_helper"
updater_signature_details="$(/usr/bin/codesign -d --verbose=4 "$updater_helper" 2>&1)"
if ! grep -Fq "Authority=$identity" <<<"$updater_signature_details"; then
  echo "error: updater helper is not signed by the requested Developer ID identity" >&2
  exit 1
fi
if ! grep -Eq 'flags=.*\(runtime\)' <<<"$updater_signature_details"; then
  echo "error: updater helper is missing hardened runtime" >&2
  exit 1
fi
if ! grep -Eq '^Timestamp=' <<<"$updater_signature_details"; then
  echo "error: updater helper is missing a secure timestamp" >&2
  exit 1
fi

# Sign every native runtime dependency and seal nested bundles inside out.
sign_nested_payload_code() {
  "$python_bin" "$repo_root/scripts/release_payload.py" sign "$1" --identity "$identity"
}

verify_target_payload_plugins() {
  "$python_bin" "$repo_root/scripts/release_payload.py" verify "$1" --identity "$identity"
}

payload_root="$out_dir/$product.app/Contents/Resources/Payload"
sign_nested_payload_code "$payload_root"

# Archive the fully signed payload so the installer app seals one immutable
# compressed-tar resource and the installer can independently verify the
# extracted plug-in before copying it.
payload_archive="$out_dir/$product.app/Contents/Resources/Payload.gmcparchive"
payload_check="$(mktemp -d /tmp/gmcp-signed-payload-check.XXXXXX)"
cleanup_payload_check() { rm -rf "$payload_check"; cleanup_build; }
trap cleanup_payload_check EXIT
rm -f "$payload_archive"
# Generic signatures on workflow resources live in extended attributes. Preserve
# them in the archive and its verification extractions.
/usr/bin/env -u COPYFILE_DISABLE /usr/bin/tar -czf "$payload_archive" -C "$(dirname "$payload_root")" "$(basename "$payload_root")"
/usr/bin/env -u COPYFILE_DISABLE /usr/bin/tar -xzf "$payload_archive" -C "$payload_check"
checked_payload="$payload_check/Payload"
verify_target_payload_plugins "$checked_payload"
payload_archive_sha256_before_signing="$(/usr/bin/shasum -a 256 "$payload_archive" | /usr/bin/awk '{print $1}')"
rm -rf "$payload_root"
echo "Embedded immutable signed payload archive: $payload_archive"

"$python_bin" "$repo_root/scripts/sign_desktop_frameworks.py" "$out_dir/$product.app/Contents/Frameworks" --identity "$identity"

echo "Signing exported app from a clean signature slot…"
/usr/bin/codesign --remove-signature "$out_dir/$product.app" 2>/dev/null || true
/usr/bin/codesign --sign "$identity" --timestamp --options runtime "$out_dir/$product.app"

# codesign can satisfy an immediate verification from the signing cache. Give
# securityd time to evict that entry so this gate exercises durable validation,
# which is what a user's Mac and Apple's notarization service will see.
sleep 15

echo "Verifying exported app signature…"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$out_dir/$product.app"
/usr/bin/codesign --verify --strict --verbose=2 "$updater_helper"

signature_details="$(/usr/bin/codesign -d --verbose=4 "$out_dir/$product.app" 2>&1)"
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
/usr/bin/env -u COPYFILE_DISABLE /usr/bin/tar -xzf "$payload_archive" -C "$payload_check"
checked_payload="$payload_check/Payload"
verify_target_payload_plugins "$checked_payload"

echo "Wrote: $out_dir/$product.app"
