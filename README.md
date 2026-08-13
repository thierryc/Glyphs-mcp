# Glyphs MCP

> [!IMPORTANT]
> **Glyphs 3 and Glyphs 4:** the `main` branch supports both major versions. The macOS installer detects each installed version and can target either or both. The terminal installer defaults to Glyphs 4; pass `--glyphs-version 3` for Glyphs 3.

Site: https://ap.cx/gmcp

A Model Context Protocol server for [Glyphs](https://glyphsapp.com) that exposes font‑specific tools to AI/LLM agents.

---

## What's new in 1.10.0 (release candidate)

**Typed LitSquare metadata and guarded start-node alignment.**

- `review_start_node_alignment` and `apply_start_node_alignment` resolve one
  explicitly selected semantic landmark across compatible masters, require an
  exact plan fingerprint, rotate only closed paths, verify complete affected
  layers, roll back on failure, and never save.
- **Glyphs MCP Metadata Inspector** adds a document-bound Palette with editable
  Font/Glyph/Layer LitSquare JSON, multi-selection replacement, and a compact
  JSON Paths editor. Valid changes commit on focus loss; invalid JSON stays
  visible without mutation. Four typed metadata tools and three typed IconGrid
  horizontal-centering tools remain available through MCP.
- The `glyphs-mcp-litsquare-metadata` skill keeps universal
  `com.litsquare.role` semantics separate from the layer opt-in at
  `com.litsquare.icongrid`. LitSquare and IconGrid writes never save.
- Italic candidates now report the first bounded topology mismatch and match
  anchors by unique names, so native collection reordering does not create a
  false topology failure.
- The server exposes 87 active tools: 76 model-visible and 11 app-only.

[Read the 1.9 roadmap →](ROADMAP.md) ·
[Read the changelog →](CHANGELOG.md) ·
[Cleanroom geometry record](content/contributor/curve-geometry-cleanroom.mdx) ·
[Experimental italic guide](content/italic-first-pass.md) ·
[Broad-Latin benchmark](content/contributor/italic-balanced-broad-latin-benchmark.md) ·
[Full-resolution three-family sheet](content/contributor/images/italic-balanced-three-family-story.png)

## macOS Installer app (recommended)

The signed and notarized Installer app is the supported end-user path. It
installs the already signed `Glyphs MCP.glyphsPlugin` without modifying its
signature, installs Python dependencies, and links Glyphs MCP into:

- Codex App
- Codex CLI (terminal tools or in VS Code)
- Claude App
- Claude CLI (terminal tools or in VS Code)

The macOS app detects Glyphs 3 and Glyphs 4 independently. If both are installed, both are selected by default; you can install or update either version alone by clearing the other checkbox. Each version keeps its own plug-in, Python, and Application Support status.

![Glyphs MCP Installer](./website/static/img/glyphs-mcp-installer.png)

- Download (DMG): https://github.com/thierryc/Glyphs-mcp/releases/latest/download/GlyphsMCPInstaller.dmg
- Download (ZIP): https://github.com/thierryc/Glyphs-mcp/releases/latest/download/GlyphsMCPInstaller.zip
- Latest release: https://github.com/thierryc/Glyphs-mcp/releases/latest

The installer can also install the bundled Glyphs MCP skills for Codex and Claude CLI.

Any MCP client compatible with the MCP protocol can use this server. For now, the automatic installer covers only the apps listed above. Because Glyphs MCP is a localhost MCP server, manual setup in other clients is usually just the endpoint URL:

```text
http://127.0.0.1:9680/mcp/
```

Terminal installer:

```bash
python3 install.py
```

In its default **Copy** mode, the terminal installer downloads the installer
ZIP for the exact version in the checkout, verifies its published SHA-256,
Developer ID signature, Team ID, notarization ticket, Gatekeeper acceptance,
and embedded plug-in signature and stapled ticket, then installs that verified
payload transactionally. The matching GitHub release must already exist and
the machine must be online.

The terminal installer targets Glyphs 4 by default. To install into Glyphs 3 explicitly, pass `--glyphs-version 3`. The macOS app instead detects and offers every installed Glyphs 3/4 target.

Finder alternative on macOS: double-click `RunInstall.command` in the repo root. It launches the same terminal installer.

To uninstall, open the app’s **Status** page and choose **Uninstall…**. The review sheet lists the exact Glyphs 3/4 plug-ins, managed skills, and matching client entries before asking for confirmation. From Terminal, preview both versions first and then run the interactive uninstall:

```bash
python3 install.py --uninstall --glyphs-version both --dry-run
python3 install.py --uninstall --glyphs-version both
```

The uninstaller intentionally preserves shared Python packages, Glyphs preferences, plug-in settings, font annotations, documents, repositories, and shared parent folders.

Scripted signed-release install example:

```bash
python3 install.py --non-interactive --python-mode glyphs --plugin-mode copy --install-skills --skills-target codex --overwrite-plugin --overwrite-skills --skip-client-guidance
```

`--plugin-mode link` is only for development from a trusted checkout. It links
mutable source code into Glyphs and provides no release-signature or
notarization guarantee.

Minimum requirements:
- macOS 13.0+
- Glyphs 3 or Glyphs 4 beta
- Python 3.11–3.14 (recommended: python.org 3.14)

Glyphs 3 backward compatibility is maintained for the shared MCP server code where possible. The macOS app can target it directly; use `--glyphs-version 3` with the terminal installer.

## Optional agent plugins

Glyphs MCP 1.10.0 provides one shared plugin package for Codex/ChatGPT, Claude
Code, Cursor, and GitHub Copilot CLI. Every host gets its own native manifest,
but all four load the same 10 skills and the same local MCP connection:

```text
http://127.0.0.1:9680/mcp/
```

Install the native Glyphs plug-in and start the server first. Then choose the
agent-plugin path only if it suits your client:

| Host | Optional plugin setup |
| --- | --- |
| Codex/ChatGPT | `codex plugin marketplace add thierryc/Glyphs-mcp` then `codex plugin add glyphs-mcp@glyphs-mcp` |
| Claude Code | `claude plugin marketplace add thierryc/Glyphs-mcp` then `claude plugin install glyphs-mcp@glyphs-mcp` |
| Cursor | Add the repository catalog with `cursor-agent plugin marketplace add https://github.com/thierryc/Glyphs-mcp` and finish in `/plugin`, or link/copy `plugins/glyphs-mcp` into `~/.cursor/plugins/local/glyphs-mcp`. |
| GitHub Copilot CLI | `copilot plugin marketplace add thierryc/Glyphs-mcp` then `copilot plugin install glyphs-mcp@glyphs-mcp` |

GitHub Copilot CLI can alternatively install the package directly:

```bash
copilot plugin install thierryc/Glyphs-mcp:plugins/glyphs-mcp
```

Plugins are an option, not a requirement. Repo-local skills, global standalone
skills, and manual MCP configuration remain supported. The macOS and terminal
installers do not install, update, or remove these agent plugins; each host owns
that lifecycle. The repository also does not enable GitHub Copilot plugins
through `.github/copilot/settings.json`.

All host manifests use version `1.10.0`. Skills inherit that package version,
while the running MCP server reports the matching native Glyphs MCP version.
See [Use agent skills and optional plugins](content/getting-started/use-agent-skills.mdx)
for install, update, removal, fallback, and host-specific invocation details.
The [Codex and ChatGPT plugin UI](content/getting-started/codex-chatgpt-plugin-ui.mdx)
page documents the richer embedded feedback panel available on compatible
OpenAI hosts; Claude, Cursor, Copilot, and other MCP clients keep the same text
and structured-result fallbacks.

## Repo skills for Codex, Claude Code, Cursor, and GitHub Copilot

This repo ships 10 workflow skills in `skills/` for common Glyphs MCP tasks.
The same source of truth is exposed through client-specific discovery paths:

- Codex, Cursor, and GitHub Copilot CLI read them through `.agents/skills`
- Claude Code reads them through `.claude/skills`

The supported usage patterns are:

### Use repo-local skills

Use this when you are developing in this repository or want the clients to discover the skills directly from the repo checkout.

1. Open this repository in Codex, Claude Code, Cursor, or GitHub Copilot CLI so the repo-local bridges are visible.
2. Connect Glyphs MCP:

```bash
codex mcp add glyphs-mcp-server --url http://127.0.0.1:9680/mcp/
codex mcp list

claude mcp add --scope user --transport http glyphs-mcp http://127.0.0.1:9680/mcp/
claude mcp list
```

3. In Codex, trust the workspace so `.agents/skills` loads.
4. In Claude Code, reload or restart if `.claude/skills` does not appear immediately.
5. In Cursor, use the repo's `.agents/skills` bridge and add the local endpoint
   to `.cursor/mcp.json`; use `.cursor/skills` only as an explicit fallback.
6. In GitHub Copilot CLI, use `.agents/skills` and add the endpoint manually
   with `copilot mcp add glyphs-mcp-server --url http://127.0.0.1:9680/mcp/ --type http`.
7. Start Glyphs and confirm the server is running in **Edit -> Glyphs MCP Server**.
8. Start with the general Glyphs launcher, or invoke a focused skill when you already know the workflow:

```text
Use $glyphs to inspect the current Glyphs context and help with my font task.
```

### Install skills globally

Use this when you want the bundled Glyphs MCP skills available without opening the repo.

1. Run the installer from the repo root, or use the signed macOS installer app:

```bash
python3 install.py
```

2. In the installer, enable **Install Glyphs MCP agent skills** for Codex and/or Claude Code.
3. The installer copies the bundled skills into:
   - `~/.codex/skills/`
   - `~/.claude/skills/`
4. Reload or restart Codex / Claude Code after the installer finishes.
5. Ask for the skill by name:

```text
Use the glyphs skill to inspect the current Glyphs context and help with my font task.
```

Advanced Codex-only alternative: you can install individual skills with Codex’s built-in `$skill-installer`, but that is not the primary Glyphs MCP workflow.

Current repo skills focus on:
- a general `$glyphs` launcher with connection and context checks
- documentation-grounded Glyphs Python script and plug-in development
- OpenType feature and stylistic-set inspection with Glyphs links
- stable Unicode and PUA assignments for icon and symbol fonts
- guarded kerning bumper reviews and applies
- guarded spacing reviews and applies
- outlines, components, anchors, and docs lookup workflows
- guarded roman-to-italic first-pass copy and slant workflows
- version, documentation, packaging, validation, signing, and publication gates

For exact per-client paths and a compatibility matrix, see
[Use skills](content/getting-started/use-agent-skills.mdx).

## What Is an MCP Server?

A *Model Context Protocol* server is a lightweight process that:

1. **Registers tools** (JSON‑RPC methods) written in the host language (Python here).  
2. **Streams JSON output** back to the calling agent. 

---

## Command Set (MCP server v1.10.0)

Glyphs MCP exposes **87 active tools** through one catalog-driven surface:
**76 are model-visible** and **11 are app-only**. Every tool has a concise
title and description, four MCP safety hints, a category, visibility, effect
class, lifecycle state, and optional structured-output schema.

The generated [command reference](https://thierryc.github.io/Glyphs-mcp/reference/command-set)
is the authoritative list. README intentionally does not duplicate the full
table. This catalog is shipped in this repo (version `1.10.0`). Typical
workflows begin with `list_open_fonts`, resolve explicit glyph
and master targets, review or preview a detached candidate, dry-run changes,
and ask for approval before confirmation. No edit tool saves implicitly.

Coordinate-only outline micro-edits use `update_glyph_node_positions` with the
font grid policy by default; `set_glyph_paths` remains the whole-path and
topology-replacement tool.

Curve work normally uses `review_curve_quality`,
`review_curve_quality_across_masters`, `set_curve_review_overlay`, and the
candidate lifecycle. Use `execute_code` only when no dedicated typed tool fits.

## Install & Setup

The simplest setup is the macOS Installer app or the terminal installer:

```bash
python3 install.py
```

The installer installs the plug-in, installs Python dependencies, and links Glyphs MCP into:

- Codex App
- Codex CLI (terminal tools or in VS Code)
- Claude App
- Claude CLI (terminal tools or in VS Code)

In the macOS app, choose Glyphs 3, Glyphs 4, or both. Missing versions remain visible but disabled, and a running unselected Glyphs version does not block the selected installation.

Optional Codex/ChatGPT, Claude Code, Cursor, and GitHub Copilot CLI agent
plugins are installed and managed separately by those hosts. Manual MCP and
standalone-skill setup remain supported.

Any MCP-compatible client can use this server. For now, the automatic installer covers only the apps above. Because this is a localhost MCP server, manual configuration in other clients is usually just the endpoint URL:

```text
http://127.0.0.1:9680/mcp/
```

For an automated signed-release install, use non-interactive mode:

```bash
python3 install.py --non-interactive --python-mode glyphs --plugin-mode copy --install-skills --skills-target codex --overwrite-plugin --overwrite-skills --skip-client-guidance
```

Copy mode fetches and verifies the exact published release matching the
checkout. Use `--plugin-mode link` only for development from a trusted
checkout; a mutable source link is not a signed or notarized distribution.

Safe uninstall preview and non-interactive removal:

```bash
python3 install.py --uninstall --glyphs-version both --dry-run
python3 install.py --uninstall --glyphs-version both --non-interactive --confirm-uninstall
```

Use repeatable `--uninstall-component plugin`, `skills`, or `clients` options to limit the removal. Without those options, all safely attributable components are reviewed. Python dependencies are never removed because their installation locations can be shared with unrelated Glyphs scripts and Python tools.

Do not copy the raw source bundle as an end-user installation. Its tracked
files are intentionally mutable and therefore cannot retain a valid
distribution signature. Use the signed installer app or terminal Copy mode.

After installation, Glyphs MCP adds two menu items:

- **Edit → Glyphs MCP Server**
- **Edit → Glyphs MCP Changes…**

The server endpoint is `http://127.0.0.1:9680/mcp/`.

### Tool discovery

Glyphs MCP exposes one catalog-driven surface. MCP Apps-aware clients show 66
substantive tools to the model and reserve 11 feedback or host-UI wrappers for
the app. Per-tool safety annotations replace the former server profiles.

Tip: If your coding agent doesn't connect to Glyphs, start the MCP server first on a fresh Glyphs launch, then launch the coding agent afterwards.

Open the **Macro Panel** to access the console.

## Resources (Helpers)

Resources are optional helpers to improve tool usage (especially code generation), not the primary feature.

- Guide: `glyphs://glyphs-mcp/guide`
- Docs directory listing: `glyphs://glyphs-mcp/docs`
- Docs index: `glyphs://glyphs-mcp/docs/index.json`

The guide defines the runtime execution contract for LLM agents:
- Read context before mutating.
- Prefer dedicated tools, then `execute_code_with_context` / `execute_code` for multi-step workflows.
- Verify changes with a read-back pass and report changed/skipped counts.

By default, per-page doc resources are not registered to avoid flooding clients.
Use `docs_search` + `docs_get` for bounded, on-demand documentation. Per-page
resource registration is not part of the public 1.9 tool surface.

## Installer Notes

- If you are unsure, accept the defaults: Glyphs Python and signed-release Copy.
- Prefer python.org Python 3.12+ over Homebrew for fewer macOS compatibility issues.
- On Apple Silicon, avoid Rosetta-translated Python builds.
- No `sudo` is required.
- Verify the local endpoint with `curl -H 'Accept: application/json' http://127.0.0.1:9680/mcp/`.

Regenerate the bundled API, scripting, plug-in-template, and file-format
documentation from the pinned official SDK and Handbook sources with:

```bash
python3 src/glyphs-mcp/scripts/generate_documentation.py
```

## Build Site Images (WebP)

Docs use a splash image at `/images/glyphs-app-mcp/glyphs-mcp.webp`.

- Requirements: Node 20+ and the `sharp` package (`npm i sharp`).
- Convert PNG assets from `content/images/glyphs-app-mcp` to WebP in `public/images/glyphs-app-mcp`:

```bash
node scripts/convert-images.mjs
```

The script ensures `glyphs-mcp.webp` (the hero image for the doc) is generated, then converts the rest.

---

## Build Development Plug-in ZIP

For local source-bundle testing only, a clean ZIP can be built without local
artifacts (`__pycache__`, `.pyc`, `.venv`, `__MACOSX`, etc.):

```bash
./scripts/build_release_zip.sh
```

Optionally override the version label used in the filename:

```bash
./scripts/build_release_zip.sh --version 1.0.0
```

The ZIP is written to `dist/` (ignored by git). It is not Developer ID signed
or notarized and must never be attached to a public release. Public releases
contain only the signed installer app ZIP, DMGs, and checksum manifest.

## Release

Installer releases are built, tested, signed, notarized, and verified locally. No GitHub Actions release job or hosted signing secret is used. See [`macos-installer/RELEASING.md`](macos-installer/RELEASING.md) for the fail-closed local workflow.

This repo ships two plugin bundle locations:

- Canonical source bundle: `src/glyphs-mcp/Glyphs MCP.glyphsPlugin`
- Glyphs Plugin Manager bundle (repo‑relative `path=` target): `plugin-manager/Glyphs MCP.glyphsPlugin`

Developer test environment:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
PYTHON_BIN=.venv/bin/python ./scripts/run_python_tests.sh
```

The runner checks Python 3.11–3.14 and required development-only modules before
starting. For a focused pytest run, use
`PYTHON_BIN=.venv/bin/python ./scripts/run_python_tests.sh --pytest <tests...>`;
the wrapper disables unrelated globally installed pytest plug-ins so they
cannot alter FastMCP/Pydantic import state. The release gate continues to use
the canonical `unittest` suite.

Release flow (copy/paste):

```bash
# Optional: do the release on a branch
git switch -c lit/release-X.Y.Z

# 1) Preview, then bump the native, installer, docs, and agent-plugin versions
python3 scripts/bump_version.py --dry-run X.Y.Z
python3 scripts/bump_version.py X.Y.Z

# 2) Synchronize and verify the shared 10-skill agent package
./scripts/sync_codex_plugin_skills.sh
./scripts/sync_codex_plugin_skills.sh --check

# 3) Build the Plugin Manager bundle from tracked files (no __pycache__, .pyc, etc.)
# This creates a self-contained Plugin Manager bundle (includes vendored deps).
./scripts/build_plugin_manager_bundle.sh --vendor
# If you already have deps installed into Glyphs' Scripts/site-packages and want an offline build:
# ./scripts/build_plugin_manager_bundle.sh --vendor-from-installed --allow-missing-targets

# 4) Run the full local release gate (Python 3.12/3.14 clean-install matrix,
#    Python and Xcode tests, unsigned Debug build; package-index access required)
./scripts/run_local_release_tests.sh

# 5) Commit release artifacts
git add README.md
git add "src/glyphs-mcp/Glyphs MCP.glyphsPlugin/Contents/Info.plist"
git add "plugin-manager/Glyphs MCP.glyphsPlugin"
git add plugins/glyphs-mcp .agents/plugins/marketplace.json
git add .claude-plugin .cursor-plugin .github/plugin
git commit -m "Release X.Y.Z"

# 6) Merge to main, then sign + push the exact reviewed tag
git tag -s "vX.Y.Z" -m "vX.Y.Z"
git push origin HEAD --tags
```

## Glyphs Plugin Manager / glyphs-packages

Glyphs MCP is not currently published in the official Glyphs Plugin Manager.
The local `plugin-manager/` bundle is a synchronization and compatibility test
fixture, not an end-user distribution.

If a future Plugin Manager submission is prepared, its entry would use `path=`
to point at the synchronized bundle:

```plist
url = "https://github.com/thierryc/Glyphs-mcp";
path = "plugin-manager/Glyphs MCP.glyphsPlugin";
dependencies = ();
```

Before enabling that entry, the Plugin Manager delivery path must pass the same
installed-bundle signature and notarization-ticket checks as the installer
paths.

## Contributing
PRs and feedback are welcome.

### Contributors
- Thierry Charbonnel (@thierryc) — Author
- Florian Pircher (@florianpircher)
- Georg Seifert (@schriftgestalt)
- Jeremy Tribby (@jpt)

---

 
