# Permanent desktop application

> Current stable 2.0.1/build 56 signing and bounded native acceptance are complete.
> See [release qualification](../V2.0.1-RELEASE.md) for actual results and outstanding
> environment/manual limits. Candidate checkpoints below are historical.


The product is **Glyphs MCP.app**, bundle identifier `cx.ap.glyphsMcp`. The Xcode project and scheme retain the historical GlyphsMCPInstaller name. Setup and the menu-bar popover share one monitor and service controls. Setup also owns the transactional component queue and agent connections. Projects supports independent template copies and read-only Git inspection. Desktop login, sidecar startup and update checks are separate preferences.

Run `python3 scripts/prepare_desktop_dependencies.py` before building to prepare
checksum-pinned Sparkle and the audited local PierreDiffsSwift package. Existing
receipts are adopted without component changes. An earlier unpublished local
candidate without the private control protocol must be stopped through its
existing controls before migration.

# Glyphs MCP local installer

This checkout contains product 2.0.1, stable-channel identity, installer build 56. The released universal app, ZIP and DMG passed Developer ID signing, notarization and Gatekeeper, and its document routes passed native VM qualification. Sidecar and bridge product versions are `2.0.1`; lean interface revision and bridge protocol are `1`. Eleven managed skills accompany seventeen tools and up to thirteen capability-gated job kinds. See [2.0.1 release qualification](../V2.0.1-RELEASE.md) and [version and identity](../content/reference/version-identity.mdx).
The native installer keeps installation on **Setup**. It offers Glyphs MCP,
Curve Inspector and Reference Inspector plus Codex, Claude Code, Claude Desktop
and Cursor connections. **Install All** reconciles every item; each card also
supports independent install, update, removal and retry. Setup also lists the
independently distributed Beztrace development preview with setup details; it
is excluded from Install All and from the bundled payload. One serialized queue
runs an atomic component transaction before configuring connectors. Existing
authentication and unrelated client configuration are preserved.

Claude Desktop and Claude Code connection removal requires an ownership receipt
and an exact match of the complete managed entry. Custom environment values,
arguments and other fields are preserved as a conflict. For an installation
created before these receipts were introduced, run the connection's **Update**
once before removal. Update retains extra user fields without adopting them;
such entries remain protected. Receipts sit beside the corresponding JSON
configuration with the `.glyphs-mcp-ownership.json` suffix.

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

The v2 payload is Glyphs 4-only. Glyphs 3 retains its separate v1.11.0
release, original Python dependency installation and version-specific skills;
the pinned v1 source metadata remains unchanged and is not embedded in this
desktop payload. Legacy updater paths reject partial upgrades to the new
component payload and direct users to the appropriate installer.

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

## Skills catalog development

Setup remains the overview. Companion Plugins, AI Agents and Skills reuse the
same installer state and operation gates. Optional skills use their own hash
receipts, advisory destination locks, atomic folder replacement and recovery
journals; they do not change the managed eleven-skill bundle or MCP interface.

`catalog-repository/` is the reproducible bootstrap for the independent
`thierryc/glyphs-mcp-skills` repository. Its registry matches the offline snapshot
in `Resources/SkillsCatalog`. Both reference the canonical bundled sources;
contributed source folders belong to the separate repository or an external
public GitHub repository. Validate with:

```sh
python catalog-repository/scripts/validate_catalog.py
python -m unittest discover -s catalog-repository/tests
```

When established runtime cache links are unavailable, retain them and use a
separate verified input folder through `GMCP_BUILD_RUNTIME_ROOT` or
`build_installer_payload.py --runtime-root`. The input identity checks still
apply. This selects build inputs only, not the installed/running runtime.
