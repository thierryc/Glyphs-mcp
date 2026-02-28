#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scheme="GlyphsMCPInstaller"

profile="${NOTARY_PROFILE:-gmcp-notary}"
identity="${CODESIGN_IDENTITY:-Developer ID Application: Thierry Charbonnel (N9U29A4T8J)}"
skip="${SKIP_NOTARIZATION:-0}"

app="$repo_root/dist/installer-app/$scheme.app"
if [[ ! -d "$app" ]]; then
  echo "error: app not found: $app" >&2
  echo "Run: ./scripts/build_installer_app.sh" >&2
  exit 1
fi

stage="$repo_root/dist/installer-dmg/stage"
out_dir="$repo_root/dist"
version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app/Contents/Info.plist" 2>/dev/null || true)"
if [[ -z "${version:-}" ]]; then
  echo "error: could not read CFBundleShortVersionString from app Info.plist" >&2
  exit 1
fi

dmg_versioned="$out_dir/$scheme-$version.dmg"
dmg_latest="$out_dir/$scheme.dmg"

rm -rf "$stage"
mkdir -p "$stage"

cp -R "$app" "$stage/$scheme.app"
ln -s /Applications "$stage/Applications"

rm -f "$dmg_versioned" "$dmg_latest"

echo "Creating DMG: $dmg_versioned"
hdiutil create -volname "$scheme" -srcfolder "$stage" -ov -format UDZO "$dmg_versioned"

if [[ "$skip" == "1" ]]; then
  cp -f "$dmg_versioned" "$dmg_latest"
  echo "Skipping notarization (SKIP_NOTARIZATION=1)."
  echo "Done: $dmg_versioned"
  echo "Also wrote: $dmg_latest"
  exit 0
fi

echo "Notarizing DMG (profile: $profile)…"
if ! xcrun notarytool submit "$dmg_versioned" --keychain-profile "$profile" --wait; then
  echo "" >&2
  echo "error: notarization failed (missing profile or auth error)." >&2
  echo "Create the profile once via:" >&2
  echo "  xcrun notarytool store-credentials $profile --team-id <TEAM_ID> --apple-id <APPLE_ID> --password <APP_SPECIFIC_PASSWORD>" >&2
  exit 1
fi

echo "Stapling DMG…"
xcrun stapler staple "$dmg_versioned"

cp -f "$dmg_versioned" "$dmg_latest"
echo "Done: $dmg_versioned"
echo "Also wrote: $dmg_latest"
