# Glyphs MCP Installer (macOS)

This folder contains a small SwiftUI macOS app that installs the Glyphs MCP plug‑in and configures common MCP clients.

## Bundle ID

- `cx.ap.glyphsMcpServerInstaller`

## Signing / notarization (Developer ID, not Mac App Store)

Prereqs:
- An Apple Developer team with a **Developer ID Application** certificate installed in your login keychain.
- `xcrun notarytool` configured (recommended: keychain profile).

One-time notarytool setup example:

```bash
xcrun notarytool store-credentials gmcp-notary \
  --team-id N9U29A4T8J \
  --apple-id "<your apple id>" \
  --password "<app-specific-password>"
```

## Build (local)

Open the project in Xcode:

- `macos-installer/GlyphsMCPInstaller/GlyphsMCPInstaller.xcodeproj`

Minimum requirements:
- macOS 13.0+
- Glyphs 3
- Python 3.11–3.13 (recommended: python.org 3.12)

Notes for Xcode builds:
- Debug builds use **Apple Development** signing (Team `D8YF5BKVYN`) so the app can run locally from Xcode.
- Release builds use **Developer ID Application** signing (Team `N9U29A4T8J`) for distribution outside the Mac App Store.
- If you change signing teams/certs, run `Product > Clean Build Folder…` and delete this project’s DerivedData to avoid mixed-signature crashes (the app and embedded framework must be signed by the same Team ID).
- If you see `Sandbox: rsync(...) deny file-write-create ...` during the `Copy Payload` build phase, ensure the build setting **Enable User Script Sandboxing** is set to `No` (we set `ENABLE_USER_SCRIPT_SANDBOXING = NO` in the project).
- If you want a per-project DerivedData location (instead of the global default): `File > Project Settings…` → **Derived Data** → `Custom` (or `Relative to Project`).

Or use scripts from repo root:

```bash
./scripts/generate_installer_appicon_assets.sh
./scripts/build_installer_app.sh
./scripts/notarize_installer_app.sh
./scripts/make_installer_dmg.sh
```

## Releasing

See `macos-installer/RELEASING.md`.

Environment variables:
- `CODESIGN_IDENTITY` (defaults to `Developer ID Application: Thierry Charbonnel (N9U29A4T8J)`)
- `NOTARY_PROFILE` (defaults to `gmcp-notary`)
- `DERIVED_DATA_PATH` (defaults to `/tmp/gmcp-installer-deriveddata`)
