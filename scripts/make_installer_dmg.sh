#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
scheme="${GLYPHS_MCP_APP_NAME:-Glyphs MCP}"

python_bin="${PYTHON_BIN:-python3}"
profile="${NOTARY_PROFILE:-gmcp-notary}"
identity="${CODESIGN_IDENTITY:-Developer ID Application: Thierry Charbonnel (N9U29A4T8J)}"
skip="${SKIP_NOTARIZATION:-0}"

app="$repo_root/dist/installer-app/$scheme.app"
background="$repo_root/macos-installer/DMG/background.tiff"
background_1x="$repo_root/macos-installer/DMG/background.png"
background_2x="$repo_root/macos-installer/DMG/background@2x.png"
if [[ ! -d "$app" ]]; then
  echo "error: app not found: $app" >&2
  echo "Run: ./scripts/build_installer_app.sh" >&2
  exit 1
fi
if [[ ! -f "$background" ]]; then
  echo "error: DMG background not found: $background" >&2
  echo "Render the 1x/2x DMG background from macos-installer/DMG/background.svg." >&2
  exit 1
fi

for representation in "$background_1x:680:420" "$background_2x:1360:840"; do
  image="${representation%%:*}"
  dimensions="${representation#*:}"
  expected_width="${dimensions%%:*}"
  expected_height="${dimensions##*:}"
  if [[ ! -f "$image" ]]; then
    echo "error: DMG background representation not found: $image" >&2
    exit 1
  fi
  image_width="$(/usr/bin/sips -g pixelWidth "$image" 2>/dev/null | awk '/pixelWidth:/ {print $2}')"
  image_height="$(/usr/bin/sips -g pixelHeight "$image" 2>/dev/null | awk '/pixelHeight:/ {print $2}')"
  if [[ "$image_width" != "$expected_width" || "$image_height" != "$expected_height" ]]; then
    echo "error: $(basename "$image") must be ${expected_width}x${expected_height} pixels (found ${image_width:-?}x${image_height:-?})" >&2
    exit 1
  fi
done
tiff_directories="$(/usr/bin/tiffutil -info "$background" | grep -c '^Directory at')"
if [[ "$tiff_directories" != "2" ]]; then
  echo "error: DMG background must contain 1x and 2x image representations" >&2
  exit 1
fi

stage="$repo_root/dist/installer-dmg/stage"
out_dir="$repo_root/dist"
version="$(/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$app/Contents/Info.plist" 2>/dev/null || true)"
if [[ -z "${version:-}" ]]; then
  echo "error: could not read CFBundleShortVersionString from app Info.plist" >&2
  exit 1
fi

release_version="$("$python_bin" "$repo_root/scripts/desktop_release_identity.py" --field releaseVersion)"
release_channel="$("$python_bin" "$repo_root/scripts/desktop_release_identity.py" --field channel)"
version="$release_version"
dmg_versioned="$out_dir/Glyphs-MCP-$version.dmg"
dmg_latest="$out_dir/Glyphs-MCP-latest.dmg"
if [[ "$skip" == "1" ]]; then
  dmg_versioned="$out_dir/Glyphs-MCP-$version-UNNOTARIZED.dmg"
fi

if [[ "$skip" != "1" ]]; then
  /usr/bin/codesign --verify --deep --strict --verbose=2 "$app"
  xcrun stapler validate "$app"
fi

rm -rf "$stage"
mkdir -p "$stage"

cp -R "$app" "$stage/$scheme.app"
ln -s /Applications "$stage/Applications"
mkdir -p "$stage/.background"
cp "$background" "$stage/.background/background.tiff"

rm -f "$dmg_versioned"
if [[ "$release_channel" == "stable" ]]; then rm -f "$dmg_latest"; fi

echo "Creating DMG: $dmg_versioned"
# Using `hdiutil create -srcfolder` mounts the staging image under /Volumes/<volname>
# during population. On newer macOS setups, Privacy/TCC restrictions can block
# access to /Volumes for Terminal shells, causing:
#   could not access /Volumes/<volname>/<app> - Operation not permitted
#
# To avoid that, create a temporary writable image, attach it to a mountpoint
# under /tmp (not /Volumes), copy the staged contents, then convert to UDZO.
tmp_root="$(mktemp -d "/tmp/gmcp-installer-dmg.XXXXXX")"
mnt="$tmp_root/mnt"
mkdir -p "$mnt"
device=""
cleanup() {
  if [[ -n "${device:-}" ]]; then
    hdiutil detach -force "$device" >/dev/null 2>&1 || true
  fi
  rm -rf "$tmp_root"
}
trap cleanup EXIT

rw_image="$tmp_root/$scheme-rw.dmg"

# Estimate required size (+ slack) in KiB.
kb="$(du -sk "$stage" | awk '{print $1}')"
kb="${kb:-0}"
kb=$((kb + 30000)) # + ~30MB slack
if [[ "$kb" -lt 50000 ]]; then
  kb=50000
fi

echo "Creating writable image (size: ${kb}k)…"
hdiutil create -size "${kb}k" -fs HFS+ -volname "$scheme" -type UDIF -ov "$rw_image" >/dev/null

device="$(hdiutil attach -nobrowse -noverify -noautoopen -mountpoint "$mnt" "$rw_image" | head -n 1 | awk '{print $1}')"
if [[ -z "${device:-}" ]]; then
  echo "error: failed to attach writable image" >&2
  exit 1
fi

echo "Populating image at: $mnt"
/usr/bin/ditto "$stage" "$mnt"

echo "Applying Finder window layout…"
/usr/bin/osascript - "$mnt" "$scheme" <<'APPLESCRIPT'
on run argv
  set folderPath to item 1 of argv
  set appName to (item 2 of argv) & ".app"
  set mountedFolder to POSIX file folderPath as alias
  set backgroundFile to POSIX file (folderPath & "/.background/background.tiff") as alias
  tell application "Finder"
    open mountedFolder
    delay 1
    set dmgWindow to front Finder window
    set current view of dmgWindow to icon view
    set toolbar visible of dmgWindow to false
    set statusbar visible of dmgWindow to false
    set pathbar visible of dmgWindow to false
    set bounds of dmgWindow to {100, 100, 780, 548}
    set viewOptions to the icon view options of dmgWindow
    set arrangement of viewOptions to not arranged
    set icon size of viewOptions to 112
    set text size of viewOptions to 12
    set background picture of viewOptions to backgroundFile
    -- Positions belong to the icon-view window. Addressing the mounted folder
    -- can leave Finder's default alphabetical layout in the saved .DS_Store.
    set position of item appName of dmgWindow to {170, 194}
    set position of item "Applications" of dmgWindow to {510, 194}
    update mountedFolder without registering applications
    delay 2
    close dmgWindow
    delay 1

    -- Reopen the image before conversion and fail closed unless Finder actually
    -- persisted the intended app → Applications layout.
    open mountedFolder
    delay 1
    set verifiedWindow to front Finder window
    set appPosition to position of item appName of verifiedWindow
    set applicationsPosition to position of item "Applications" of verifiedWindow
    if appPosition is not equal to {170, 194} then
      error "Finder did not persist the application icon position: " & appPosition
    end if
    if applicationsPosition is not equal to {510, 194} then
      error "Finder did not persist the Applications icon position: " & applicationsPosition
    end if
    close verifiedWindow
  end tell
end run
APPLESCRIPT

# Give Finder a moment to flush .DS_Store before detaching the writable image.
/bin/sleep 1

echo "Detaching: $device"
hdiutil detach "$device" >/dev/null
device=""

echo "Converting to UDZO: $dmg_versioned"
converted_base="$tmp_root/$scheme-udzo"
hdiutil convert "$rw_image" -format UDZO -ov -o "$converted_base" >/dev/null
if [[ ! -f "${converted_base}.dmg" ]]; then
  echo "error: expected converted DMG at ${converted_base}.dmg" >&2
  exit 1
fi
mv -f "${converted_base}.dmg" "$dmg_versioned"

rm -rf "$tmp_root"

echo "Signing DMG…"
/usr/bin/codesign --force --sign "$identity" --timestamp "$dmg_versioned"
/usr/bin/codesign --verify --strict --verbose=2 "$dmg_versioned"

if [[ "$skip" == "1" ]]; then
  echo "Skipping notarization (SKIP_NOTARIZATION=1)."
  echo "Wrote a deliberately non-release artifact: $dmg_versioned"
  echo "The secure publisher will never upload this filename."
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
xcrun stapler validate "$dmg_versioned"

if [[ "$release_channel" == "stable" ]]; then
  cp -f "$dmg_versioned" "$dmg_latest"
  echo "Also wrote: $dmg_latest"
fi
echo "Done: $dmg_versioned"
