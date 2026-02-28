#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scheme="GlyphsMCPInstaller"
app="$repo_root/dist/installer-app/$scheme.app"

profile="${NOTARY_PROFILE:-gmcp-notary}"
skip="${SKIP_NOTARIZATION:-0}"

if [[ ! -d "$app" ]]; then
  echo "error: app not found: $app" >&2
  echo "Run: ./scripts/build_installer_app.sh" >&2
  exit 1
fi

zip="$repo_root/dist/installer-app/$scheme.zip"
rm -f "$zip"

echo "Zipping for notarization: $zip"
ditto -c -k --keepParent "$app" "$zip"

if [[ "$skip" == "1" ]]; then
  echo "Skipping notarization (SKIP_NOTARIZATION=1)."
  echo "Wrote (unsigned for distribution): $zip"
  exit 0
fi

echo "Submitting to notarytool (profile: $profile)…"
if ! xcrun notarytool submit "$zip" --keychain-profile "$profile" --wait; then
  echo "" >&2
  echo "error: notarization failed (missing profile or auth error)." >&2
  echo "Create the profile once via:" >&2
  echo "  xcrun notarytool store-credentials $profile --team-id <TEAM_ID> --apple-id <APPLE_ID> --password <APP_SPECIFIC_PASSWORD>" >&2
  exit 1
fi

echo "Stapling ticket…"
xcrun stapler staple "$app"

echo "Notarized + stapled: $app"
