# Releasing Glyphs MCP Installer (macOS)

This repo ships a signed + notarized (non–Mac App Store) SwiftUI installer app, distributed as a drag‑and‑drop DMG.

## Prereqs (one-time)

### Signing (Developer ID)
- Install a **Developer ID Application** certificate in your login keychain.
- The build scripts default to:
  - `Developer ID Application: Thierry Charbonnel (N9U29A4T8J)`
  - Override with `CODESIGN_IDENTITY="Developer ID Application: …"`

### Notarization (notarytool Keychain profile)
Create a Keychain profile (recommended name: `gmcp-notary`):

```bash
xcrun notarytool store-credentials gmcp-notary \
  --team-id N9U29A4T8J \
  --apple-id "<your apple id>" \
  --password "<app-specific-password>"
```

Notes:
- The password must be an **app-specific password** from `appleid.apple.com`.
- The scripts read the profile name from `NOTARY_PROFILE` (default: `gmcp-notary`).

### GitHub Releases (gh)
Authenticate GitHub CLI:

```bash
gh auth login -h github.com
```

## Versioning (what to bump)

This project keeps the installer app and the plug‑in version aligned (`X.Y.Z`).

1) **Plug‑in version** (both copies):
- `src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Info.plist`
- `plugin-manager/Glyphs MCP.glyphsPlugin/Contents/Info.plist`

Update both:
- `CFBundleShortVersionString` → `X.Y.Z`
- `CFBundleVersion` → `X.Y.Z`

2) **Installer app version** (Xcode project):
- `macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj/project.pbxproj`

Update:
- `MARKETING_VERSION` → `X.Y.Z`
- `CURRENT_PROJECT_VERSION` → increment build number (integer)

3) **Docs/links** (if needed for the new tag):
- Root `README.md` download link should match the future release asset name:
  - `GlyphsMCPInstaller-X.Y.Z.dmg`

## Build, sign, notarize, DMG

From repo root:

```bash
# Optional: refresh the AppIcon asset-catalog PNGs if you changed the SVG
./scripts/generate_installer_appicon_assets.sh

# Build signed Release app → dist/installer-app/GlyphsMCPInstaller.app
./scripts/build_installer_app.sh

# Notarize + staple the .app
./scripts/notarize_installer_app.sh

# Create DMG (app + /Applications symlink), notarize + staple
./scripts/make_installer_dmg.sh
```

Outputs:
- `dist/GlyphsMCPInstaller-X.Y.Z.dmg` (versioned)
- `dist/GlyphsMCPInstaller.dmg` (latest alias)

### Important: payload plug-in signing

Apple notarization validates **all nested executables inside the app bundle** (including the embedded payload plug‑in).

The Xcode build phase **Copy Payload** now signs and timestamps:
- `…/Contents/Resources/Payload/Glyphs MCP.glyphsPlugin/Contents/MacOS/plugin`

If notarization fails with errors like “binary is not signed” or “no secure timestamp”, rebuild the app (Release) and re-run notarization.

## QA (recommended)

Before releasing:

```bash
xcodebuild test \
  -project macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj \
  -scheme GlyphsMCPInstaller \
  -destination 'platform=macOS'
```

Optionally verify signatures:

```bash
codesign -dv --verbose=4 dist/installer-app/GlyphsMCPInstaller.app 2>&1 | head
spctl -a -vv dist/installer-app/GlyphsMCPInstaller.app
```

## Commit, tag, merge, release

Typical flow (adjust to your branching policy):

```bash
# Commit version bump + changes
git add -A
git commit -m "Release vX.Y.Z"

# Tag
git tag -a vX.Y.Z -m "vX.Y.Z"

# Merge to main (example)
git switch main
git pull --ff-only
git merge <your-release-branch>

# Push
git push origin main
git push origin vX.Y.Z
```

Create the GitHub Release and upload the DMG:

```bash
gh release create vX.Y.Z dist/GlyphsMCPInstaller-X.Y.Z.dmg \
  --title "vX.Y.Z" \
  --notes "macOS installer app (signed + notarized)."
```

## Troubleshooting

### Notarytool: “No Keychain password item found for profile”
- The profile name doesn’t exist in Keychain, or you’re running in an environment that can’t access the keychain.
- Re-run `notarytool store-credentials …` and ensure scripts run outside restrictive sandboxes.

### Notarytool: “Archive contains critical validation errors”
Fetch the log:

```bash
xcrun notarytool log <SUBMISSION_ID> --keychain-profile gmcp-notary
```

Common causes:
- A nested binary in the payload isn’t signed or lacks a secure timestamp.
- Rebuild the app and ensure the payload signing step ran.

