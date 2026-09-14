# Permanent desktop application

The product is **Glyphs MCP.app**, bundle identifier `cx.ap.glyphsMcp`. The Xcode project and scheme retain the historical GlyphsMCPInstaller name. Overview and the menu-bar popover share one monitor and service controls. Components reuses the transactional installer. Projects supports independent template copies and read-only Git inspection. Desktop login, sidecar startup and update checks are separate preferences.

Run `python3 scripts/prepare_desktop_dependencies.py` before building to prepare the checksum-pinned Sparkle framework. Existing receipts are adopted without component changes. An earlier unpublished local candidate without the private control protocol must be stopped through its existing controls before migration.

# Glyphs MCP local installer

The beta branch prepares product 2.0.0 Beta 1, release `2.0.0-beta.1`, installer build 43. Sidecar and bridge product versions are `2.0.0`; lean interface revision and bridge protocol are `1`. Eleven managed skills accompany seven tools and five job kinds. See [version and identity](../content/reference/version-identity.mdx).
The native installer uses **Choose → Install → Ready**, detects Glyphs and offers
Glyphs MCP, Curve Inspector and Reference Inspector. Fresh installs select all
three. Upgrades keep component choices; removal is explicit. AI connections
are optional and existing authentication/configuration is preserved.

Glyphs 4 uses an architecture-matched private CPython 3.14.7 runtime and locked
FastMCP 2.12.0 / glyphs-cli 0.6.1 dependencies. Installations require no package
downloads or shell configuration. Glyphs' selected scripting environment is
preflighted separately. Git is required only for Git references.

The backend stages managed components and records replacement intent before
renaming. It restores components, launch-agent configuration and receipts as
one transaction on failure, and recovers interrupted transactions before
reading upgrade choices. Ports, automatic start, authentication and welcome
preferences remain outside component replacement. Unrelated files are retained.
The Mac's normal Glyphs quit/save workflow must finish before replacement.

Glyphs 3 retains the pinned 1.11.0 bundle and its original Python dependency
installation, with its version-specific skills. Legacy updater paths reject
partial upgrades to the new component payload and direct users to the installer.

## Build locally

Use the repository's development Python for build scripts and tests. Fetch
inputs once on a connected build machine, then build offline:

```sh
python scripts/download_private_runtime.py --architecture arm64
python scripts/download_private_runtime.py --architecture x86_64
python scripts/build_private_runtime.py --architecture arm64 --output build/private-runtime/arm64
python scripts/build_private_runtime.py --architecture x86_64 --output build/private-runtime/x86_64
python scripts/build_installer_payload.py
python scripts/build_local_app.py
python scripts/verify_desktop_app.py 'dist/local/Glyphs MCP.app' \
  --receipt dist/local/build-receipt.json
```

The local builder always uses a new DerivedData directory, removes it when the
run ends, and checks the compiled image assets, linked frameworks, version and
build number. The only local install candidate is `dist/local/Glyphs MCP.app`
with its matching `build-receipt.json`. Verify the receipt immediately before
installation; it binds the entire app to this worktree and its source contents.
A failed build invalidates the old receipt. Never install a bundle found in an
old Xcode output, copied DerivedData directory, or historical build snapshot.
Build logs remain in `build/reports/local-app-build.log`.

Use `python scripts/clean_desktop_builds.py` to inspect obsolete generated
outputs and add `--apply` to remove them. It preserves source snapshots,
validation reports, pinned runtimes and downloaded dependencies. Never delete
`build/` wholesale: some development checkouts contain nested Git worktrees.
Create new worktrees beside the repository, outside generated-output folders.

The commands above build an unsigned Debug app. For the universal Developer
ID-signed distribution, follow [RELEASING.md](RELEASING.md). That local workflow
covers private runtimes, the bridge and companions, Apple notarization and
verified GitHub version discovery, without release Actions. Public publication
and the final welcome design remain separate from local candidate acceptance.

Run `scripts/run_local_release_tests.sh` with `PYTHON_BIN` set for tests,
component determinism, skill/docs checks and unsigned candidate verification.
The actual Glyphs acceptance gate additionally requires an unlocked Mac and a
disposable font. Record baseline and loaded timings independently; 200 ms is
a diagnostic threshold, never an automatic rejection.
