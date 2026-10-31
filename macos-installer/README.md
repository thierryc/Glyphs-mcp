# Permanent desktop application

> Published stable **2.5.0/build 73** is signed, notarized and published.
> See [release qualification](../V2.5.0-RELEASE.md) for the full gate, exact distribution checks and retained limits. Candidate checkpoints below are historical.

The product is **Glyphs MCP.app**, bundle identifier `cx.ap.glyphsMcp`. The Xcode project and scheme retain the historical GlyphsMCPInstaller name. Setup and the native menu-bar menu share one monitor and service controls. Tasks provides task status, blockers, conversation handoff and guarded recovery for abandoned work; see [Companion Tasks](../docs/companion-tasks.md). Setup also owns the transactional component queue and agent connections. Projects supports independent template copies and read-only Git inspection. Desktop login, sidecar startup and update checks are separate preferences.

Prior stable **2.4.0/build 71** adds simpler task states, document-scoped recovery, precise blockers, inactive-task expiry and source-bound typed exports. See [release qualification](../V2.4.0-RELEASE.md).

Run `python3 scripts/prepare_desktop_dependencies.py` before building to prepare
checksum-pinned Sparkle and the audited local PierreDiffsSwift package. Existing
receipts are adopted without component changes. An earlier unpublished local
candidate without the private control protocol must be stopped through its
existing controls before migration.

# Glyphs MCP local installer

The earlier patch is **2.3.1/build 69**, with optional development skills in
Connections. See [patch qualification](../V2.3.1-RELEASE.md).

The earlier 2.2.0/build 67 baseline shipped with twenty-one data/action tools,
one optional display tool and eleven managed skills. Its sidecar and bridge product
versions were 2.2.0; interface revision and bridge protocol remain 1. Earlier
signing and acceptance evidence retains its original build scope. See
[2.2.0 release qualification](../V2.2.0-RELEASE.md), including the VM progress-window
limitation and Rosetta-only Intel coverage. Prior 2.1.0 assets remain available.
The native installer keeps installation on **Setup**. It offers Glyphs MCP,
Curve Inspector and Reference Inspector plus Codex, Claude Code, Claude Desktop
and Cursor connections. **Install All** reconciles every item; each card also
supports independent install, update, removal and retry. Setup also lists the
optional managed Beztrace card. Managed Beztrace setup is qualified on Apple Silicon with macOS 26.6.2 or later;
Diffenator is deferred beyond 2.3.0 and is not offered in Setup. Beztrace is excluded from Install All. One serialized queue
runs an atomic component transaction before configuring connectors. Existing
authentication and unrelated client configuration are preserved.
Existing modified or unowned skills are kept in place and reported as
information under **Configured**. Successful setup uses a positive informational
summary; actual configuration failures retain their error details.

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

## Font package copies in Projects

Projects opens in **Diff**, where the Git browser fills the workspace below a
compact project header. Use the **Diff / Config** segmented control to switch
views without resetting the current diff selection or zoom. **Config** contains
font sources, project settings and the actions for opening external tools. Font
sources are scanned when Config is opened.

The **Font sources** list in Config includes saved `.glyphs` files and `.glyphspackage`
folders regardless of Git status. Use a source’s three-dot or right-click menu
and choose **Create Package Copy…**. The filename is editable; the destination
stays beside the source, and existing destinations are never replaced.

Copies use the bundled CLI and the selected Glyphs 4 application without a live
MCP connection. They include saved contents only, keep the original, and leave
open documents and Git staging unchanged. Native package serialization may omit
per-glyph modification timestamps. The worker reopens and compares the package,
checks image references and the source hash, then publishes it atomically.

Run `python3 scripts/qualify_package_copy.py --app '/Applications/Glyphs 4.app'`
for disposable native round trips, including quartic curves and shape groups.

## Build locally

In Project → Browse Templates, each template has a Preview action for its folder
structure and file contents. Built-in, pinned GitHub and local templates use the
same browser. Previewing downloads a GitHub template when needed but does not
create a project. Use Template continues to the naming step; Preview Project
shows the selected name and connection values substituted into the exact file
snapshot used by Create Project. Text is selectable, images have inline previews,
and other binary files show their size. Long text previews are limited to 256 KB.

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

The desktop views share their visual components in `Sources/ModernStyle.swift`.
`DesktopCatalogCard` provides the title, description, status, actions and footer
layout, with optional artwork for components and agents. Skills omit the artwork;
project templates and grouped panels reuse `DesktopCardSurface`.
`DesktopStatus` uses plain green installed indicators, neutral uninstalled states
and progress spinners. `DesktopActionButton` uses system capsule buttons: blue
for installation and neutral for update/uninstall. `DesktopActionRow` stacks
actions when a narrow card or a translation needs more room. Every hosted window
applies `desktopDesign()` so settings, sheets and other actions use the same
control shape. Supporting URLs use `DesktopTextLink` to remain plain blue links.
Keep navigation rows, menus and diff-tool controls in their
appropriate native styles.

Setup remains the overview. Companion Plugins, AI Agents and Skills reuse the
same installer state and operation gates. Optional skills use their own hash
receipts, advisory destination locks, atomic folder replacement and recovery
journals; they do not change the managed twelve-skill bundle or MCP interface.

The skill details sheet has independent Install / Update and Remove controls for
each compatible local agent. Personal discovery includes the shared
`.agents/skills` folder and older `.codex/skills` and `.cursor/skills` locations;
actions use the detected location. Project discovery stays within that project.
Existing or edited regular copies require confirmation and a verified backup
before updating. Removal also keeps a backup. Updating a linked skill requires
explicit confirmation to replace only the link with a managed catalog copy,
backing up the link and preserving its source folder. Remove detaches and backs
up only the link. Interrupted updates can restore the original link.
Locations and operation details are available in an expandable section.

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

Quit the local candidate before running `scripts/build_local_app.py`. The builder
refuses to overwrite a running app at `dist/local/Glyphs MCP.app` and preserves
the candidate and receipt if it cannot check running processes. For manual tests,
use one freshly launched desktop instance so older windows cannot be mistaken
for the current build. The Glyphs application and sidecar remain separate.
