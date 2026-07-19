# Releasing Glyphs MCP Installer (macOS)

This repo ships a signed + notarized (non–Mac App Store) SwiftUI installer app, distributed as a drag‑and‑drop DMG. The release build, tests, signing, notarization, verification, and upload all run locally. GitHub Actions is not used for installer releases, and no signing credentials are stored on GitHub.

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
- Root `README.md` and installer docs should reflect the current client matrix:
  - Codex
  - Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`)
  - Claude Code (`~/.claude.json`)
- Root `README.md` download link should match the future release asset name:
  - `GlyphsMCPInstaller-X.Y.Z.dmg`

## Local release test gate

Run the same mandatory test gate used by the publisher:

```bash
./scripts/run_local_release_tests.sh
```

It runs the complete Python suite, the complete Xcode test suite, shell syntax checks, patch whitespace checks, and an unsigned Debug installer build. The Debug build is deliberately unsigned because it is only a local compilation check. Distribution artifacts are built separately in Release configuration and must have a valid Developer ID signature, hardened runtime, secure timestamp, notarization ticket, and Gatekeeper acceptance.

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

# Verify every artifact and write its exact SHA-256 manifest
./scripts/verify_release_artifacts.sh --tag vX.Y.Z --write-checksums
```

Outputs:
- `dist/GlyphsMCPInstaller-X.Y.Z.dmg` (versioned)
- `dist/GlyphsMCPInstaller.dmg` (latest alias)
- `dist/installer-app/GlyphsMCPInstaller.zip` (contains the stapled app)
- `dist/SHA256SUMS` (exact release artifact set)

The verifier checks source/Xcode/built versions, Developer ID authority and Team ID, nested payload signatures, hardened runtime, secure timestamps, stapled tickets, Gatekeeper, ZIP contents, byte-identical latest/versioned DMGs, and the exact checksum set.

`SKIP_NOTARIZATION=1` is for local diagnostics only. It creates filenames containing `UNNOTARIZED`; the publisher refuses to run in that mode and never uploads those files.

### Important: payload plug-in signing

Apple notarization validates **all nested executables inside the app bundle** (including the embedded payload plug‑in).

The Xcode build phase **Copy Payload** now signs and timestamps:
- `…/Contents/Resources/Payload/Glyphs MCP.glyphsPlugin/Contents/MacOS/plugin`

If notarization fails with errors like “binary is not signed” or “no secure timestamp”, rebuild the app (Release) and re-run notarization.

## QA

The local test gate is mandatory before publishing. It can also be run independently:

```bash
./scripts/run_local_release_tests.sh
```

To rebuild and verify locally without uploading:

```bash
./scripts/publish_release_assets.sh --tag vX.Y.Z --dry-run
```

This dry run still requires a clean `main`, an annotated tag at `HEAD`, a matching remote `main` and remote tag, and a valid tag signature by default.

## Commit, tag, and local publish

Prepare the release changes on a branch, merge them to `main`, then create a signed annotated tag on the exact reviewed commit:

```bash
git add -A
git commit -m "Release vX.Y.Z"
git switch main
git pull --ff-only
git merge <your-release-branch>
git push origin main

git tag -s vX.Y.Z -m "vX.Y.Z"
git push origin vX.Y.Z
```

If signed tags are not configured, `--allow-unsigned-tag` is an explicit escape hatch for an annotated tag after manual commit review. A lightweight tag is never accepted.

Create an empty draft release, then run the local publisher:

```bash
gh release create vX.Y.Z --verify-tag --draft \
  --title "vX.Y.Z" \
  --notes "macOS installer app (signed + notarized)."

# Build and verify without uploading first
./scripts/publish_release_assets.sh --tag vX.Y.Z --dry-run

# Reuse those artifacts, re-run all tests and verification, then upload
./scripts/publish_release_assets.sh --tag vX.Y.Z --skip-build \
  --confirm-publish vX.Y.Z
```

The exact tag confirmation is required for non-interactive use; an interactive terminal asks you to type it. The script refuses dirty worktrees, non-`main` branches, stale or mismatched remote commits/tags, unsigned tags by default, published releases, pre-existing asset names, skipped notarization, signature/notary failures, and checksum drift. It does not overwrite release assets. The release stays a draft after upload so its notes and asset list can be reviewed before publication.

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

### The release is not a draft or already contains an asset

The publisher intentionally refuses to modify an already-published release or overwrite an existing asset. Review the remote state. For a new release, use an empty draft. Do not delete or replace a public artifact merely to bypass this gate; publish a new patch version when an artifact has already been distributed.
