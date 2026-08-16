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

3) **Optional agent plugin manifests**:
- `plugins/glyphs-mcp/.codex-plugin/plugin.json`
- `plugins/glyphs-mcp/.claude-plugin/plugin.json`
- `plugins/glyphs-mcp/.cursor-plugin/plugin.json`
- `plugins/glyphs-mcp/.github/plugin/plugin.json`

Set every manifest's `version` to `X.Y.Z`. Marketplace entries deliberately do
not duplicate the package version. The 11 skills inherit the package version,
and `.mcp.json` stays shared across hosts.

4) **Docs/links** (if needed for the new tag):
- Root `README.md` and installer docs should reflect the current client matrix:
  - Codex
  - Claude Desktop (`~/Library/Application Support/Claude/claude_desktop_config.json`)
  - Claude Code (`~/.claude.json`)
  - Cursor (optional host plugin or manual MCP)
  - GitHub Copilot CLI (optional host plugin or manual MCP)
- Root `README.md` download link should match the future release asset name:
  - `GlyphsMCPInstaller-X.Y.Z.dmg`

## Local release test gate

Preview version alignment and verify the shared skill package before the full
gate:

```bash
python3 scripts/bump_version.py --dry-run X.Y.Z
./scripts/sync_codex_plugin_skills.sh --check
```

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

The verifier checks source/Xcode/built versions, Developer ID authority and Team ID, the extracted `Payload.gmcparchive` signatures, hardened runtime, secure timestamps, stapled tickets, Gatekeeper, ZIP contents, byte-identical latest/versioned DMGs, and the exact checksum set. It also copies the embedded plug-in into a temporary Glyphs plug-ins directory and requires the installed copy to preserve the executable bytes and Developer ID signature.

There is deliberately no standalone `Glyphs MCP.glyphsPlugin.zip` release
asset. The mutable tracked source bundle does not carry the release's Developer
ID seal. End users receive the plug-in only through the signed, notarized
installer app.

`SKIP_NOTARIZATION=1` is for local diagnostics only. It creates filenames containing `UNNOTARIZED`; the publisher refuses to run in that mode and never uploads those files.

### Important: nested payload signing

The release pipeline validates **all executable code it ships**, including the
plug-in and the pinned SDK executables inside the managed development skill.
Apple notarization validates the installer app and framework; the local release
verifier independently extracts and validates the archived payload before and
after notarization.

Because `Payload.gmcparchive` is opaque to the installer app's notarization
submission, `notarize_installer_app.sh` also extracts the exact signed main
plug-in and submits a temporary ZIP of that unchanged code hash to Apple. It
then staples and validates Apple's ticket on the custom `.glyphsPlugin`,
rebuilds the opaque payload archive, and re-signs the outer app before
submitting that exact app to Apple. The temporary plug-in ZIP is never a
release asset.

The Release export step removes stale/ad-hoc signatures, then signs and
timestamps every Mach-O executable under:

- `…/Contents/Resources/Payload/**/Contents/MacOS/*`

This includes the main Glyphs MCP plug-in executable and the pinned SDK
executables inside plug-in templates shipped with the
`glyphs-mcp-development` skill.

After the loaders are signed, it seals every Glyphs code bundle
(`.glyphsPlugin`, `.glyphsReporter`, `.glyphsTool`, `.glyphsFilter`,
`.glyphsFileFormat`, and `.glyphsPalette`) from the deepest bundle outward and
verifies the complete resource seal. It then stores the signed payload as
`Contents/Resources/Payload.gmcparchive`, removes the unpacked payload, signs
the outer app, waits for the signing cache to expire, and verifies the archive
bytes and every extracted signature again.

If notarization fails with errors like “binary is not signed” or “no secure timestamp”, rebuild the app (Release) and re-run notarization.

The installer must not re-sign the plug-in after copying it. Its transactional
install compares the source, staged, and installed CDHash and Team ID. A
mismatch restores the previous bundle and fails the installation.
Both macOS-app and terminal Copy installations also require Gatekeeper to
accept the installer application and require Apple's stapler validator to
accept the extracted plug-in ticket before staging it. `spctl --type execute`
is not used on `.glyphsPlugin` because that assessment is defined for
applications and rejects custom bundles as “does not seem to be an app.”

### Verified update preparation contract

Version 1.6.0 introduces staging, not automatic installation. The signed macOS
installer can opt Glyphs 3 and Glyphs 4 into a fixed verified helper. In the
plug-in, **Prepare Update** downloads and verifies one exact later release and
stages its plug-in without editing the running or installed bundle. A ready
stage must keep **View Release** available so the user can run the signed
installer separately. Users on 1.5.4 install 1.6.0 manually because 1.5.4 does
not contain this helper. Do not describe this workflow as automatic or in-app
installation.

## QA

The local test gate is mandatory before publishing. It can also be run independently:

```bash
./scripts/run_local_release_tests.sh
```

For 1.5.4 and later, also run the installer ABI matrix before signing:

- Glyphs 3.5 with its exact selected Python and Glyphs 3
  `Scripts/site-packages`.
- Glyphs 4 with its exact selected Python and Glyphs 4
  `Scripts/site-packages`.
- A clean/incomplete fixture, which must pass preflight and continue to pip.
- A Python 3.14 fixture containing `cpython-311` builds of
  `pydantic_core` and `objc`, which must fail at **Check Python environment**.
- Compatible CPython, `.abi3`, and universal-binary fixtures, which must pass.

For every blocking fixture, capture the installer log and prove that pip,
plug-in replacement, and client configuration did not run. Then prove a
post-install missing import, malformed JSON, nonzero exit, timeout, unexpected
origin, and stderr-only failure prevents the **Done** state. Repeat the
preflight boundary in terminal interactive and non-interactive modes; terminal
failures must exit with status `2`.

Signed-bundle bytecode-cache handling is a separate known packaging task. Keep
excluding `__pycache__` and `.pyc` artifacts from release payloads, but do not
combine a cache-policy change with the 1.5.4 ABI diagnostic patch.

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

The exact tag confirmation is required for non-interactive use; an interactive terminal asks you to type it. The script refuses dirty worktrees, non-`main` branches, stale or mismatched remote commits/tags, unsigned tags by default, published releases, pre-existing asset names, skipped notarization, signature/notary failures, and checksum drift. It uploads only the versioned/latest DMGs, signed installer app ZIP, and checksum manifest; it never uploads a standalone plug-in ZIP. It does not overwrite release assets. The release stays a draft after upload so its notes and asset list can be reviewed before publication.

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
