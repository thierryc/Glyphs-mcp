#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scheme="GlyphsMCPInstaller"
app="$repo_root/dist/installer-app/$scheme.app"

profile="${NOTARY_PROFILE:-gmcp-notary}"
skip="${SKIP_NOTARIZATION:-0}"
identity="${CODESIGN_IDENTITY:-Developer ID Application: Thierry Charbonnel (N9U29A4T8J)}"

if [[ ! -d "$app" ]]; then
  echo "error: app not found: $app" >&2
  echo "Run: ./scripts/build_installer_app.sh" >&2
  exit 1
fi

zip="$repo_root/dist/installer-app/$scheme.zip"
if [[ "$skip" == "1" ]]; then
  zip="$repo_root/dist/installer-app/$scheme-UNNOTARIZED.zip"
fi
rm -f "$zip"

if [[ "$skip" == "1" ]]; then
  echo "Zipping deliberately unnotarized app: $zip"
  ditto -c -k --keepParent "$app" "$zip"
  echo "Skipping notarization (SKIP_NOTARIZATION=1)."
  echo "Wrote a deliberately non-release artifact: $zip"
  echo "The secure publisher will never upload this filename."
  exit 0
fi

payload_archive="$app/Contents/Resources/Payload.gmcparchive"
if [[ ! -f "$payload_archive" ]]; then
  echo "error: signed installer payload archive not found: $payload_archive" >&2
  exit 1
fi

notary_tmp="$(mktemp -d /tmp/gmcp-notary-payload.XXXXXX)"
cleanup_notary_tmp() { rm -rf "$notary_tmp"; }
trap cleanup_notary_tmp EXIT
/usr/bin/tar -xzf "$payload_archive" -C "$notary_tmp"
plugin="$notary_tmp/Payload/Glyphs MCP.glyphsPlugin"
if [[ ! -d "$plugin" ]]; then
  echo "error: signed installer payload does not contain Glyphs MCP.glyphsPlugin" >&2
  exit 1
fi
/usr/bin/codesign --verify --deep --strict --verbose=2 "$plugin"

# Payload.gmcparchive is intentionally opaque to the outer app signature.
# Submit the exact plug-in code hash separately so Gatekeeper can accept the
# installed bundle after it is copied out of the notarized installer.
plugin_zip="$notary_tmp/GlyphsMCPNotaryPayload.zip"
/usr/bin/ditto -c -k --keepParent "$plugin" "$plugin_zip"
echo "Submitting exact plug-in payload to notarytool (profile: $profile)…"
if ! xcrun notarytool submit "$plugin_zip" --keychain-profile "$profile" --wait; then
  echo "" >&2
  echo "error: plug-in payload notarization failed." >&2
  exit 1
fi

# A .glyphsPlugin is a custom code bundle, not an application. spctl's
# execute assessment rejects it as "does not seem to be an app" even after
# Apple accepts the notarization submission. Staple the accepted ticket to
# the exact custom bundle and require Apple's ticket validator instead.
echo "Stapling exact plug-in ticket…"
xcrun stapler staple "$plugin"
xcrun stapler validate "$plugin"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$plugin"
if [[ ! -f "$plugin/Contents/CodeResources" ]]; then
  echo "error: stapled plug-in ticket is missing from Contents/CodeResources" >&2
  exit 1
fi

# The stapled ticket changes the opaque payload archive, which is sealed by
# the outer app. Rebuild the archive and re-sign the app before submitting the
# final app bytes to Apple.
stapled_payload_archive="$notary_tmp/Payload.gmcparchive"
COPYFILE_DISABLE=1 /usr/bin/tar -czf "$stapled_payload_archive" -C "$notary_tmp" Payload
/bin/mv "$stapled_payload_archive" "$payload_archive"
echo "Re-signing installer app with stapled plug-in payload…"
/usr/bin/codesign --remove-signature "$app" 2>/dev/null || true
/usr/bin/codesign --sign "$identity" --timestamp --options runtime "$app"
sleep 15
/usr/bin/codesign --verify --deep --strict --verbose=2 "$app"
updater_helper="$app/Contents/Resources/GlyphsMCPUpdater"
if [[ ! -f "$updater_helper" || -L "$updater_helper" ]]; then
  echo "error: signed updater helper is missing from the installer app" >&2
  exit 1
fi
/usr/bin/codesign --verify --strict --verbose=2 "$updater_helper"

echo "Zipping for notarization: $zip"
ditto -c -k --keepParent "$app" "$zip"

echo "Submitting installer app to notarytool (profile: $profile)…"
if ! xcrun notarytool submit "$zip" --keychain-profile "$profile" --wait; then
  echo "" >&2
  echo "error: notarization failed (missing profile or auth error)." >&2
  echo "Create the profile once via:" >&2
  echo "  xcrun notarytool store-credentials $profile --team-id <TEAM_ID> --apple-id <APPLE_ID> --password <APP_SPECIFIC_PASSWORD>" >&2
  exit 1
fi

echo "Stapling ticket…"
xcrun stapler staple "$app"
xcrun stapler validate "$app"
/usr/bin/codesign --verify --deep --strict --verbose=2 "$app"
xcrun stapler validate "$plugin"
/usr/bin/codesign --verify --strict --verbose=2 "$updater_helper"

# Recreate the ZIP after stapling so the uploaded archive contains the ticket.
rm -f "$zip"
ditto -c -k --keepParent "$app" "$zip"

echo "Notarized + stapled: $app"
echo "Repacked stapled app: $zip"
