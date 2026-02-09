# Glyphs MCP
Site: https://ap.cx/gmcp

A Model Context Protocol server for [Glyphs](https://glyphsapp.com) that exposes font‑specific tools to AI/LLM agents.

---

Quick install (interactive):

```bash
python3 install.py
```

On macOS Finder you can also double‑click `RunInstall.command` in the repo root; it launches the same installer (`python3 install.py`). If Gatekeeper blocks it, right‑click → Open once to approve.

## What Is an MCP Server?

A *Model Context Protocol* server is a lightweight process that:

1. **Registers tools** (JSON‑RPC methods) written in the host language (Python here).  
2. **Streams JSON output** back to the calling agent. 

---

## Command Set (MCP server v1.0.0)

This table describes the tool surface exposed by the MCP server shipped in this repo (FastMCP `version="1.0.0"`).

| Tool | Description |
|------|-------------|
| `list_open_fonts` | List all open fonts and basic metadata. |
| `get_font_glyphs` | Return glyph list and key attributes for a font. |
| `get_font_masters` | Detailed master information for a font. |
| `get_font_instances` | List instances and their interpolation data. |
| `get_glyph_details` | Full glyph data including layers, paths, components. |
| `get_font_kerning` | All kerning pairs for a given master. |
| `create_glyph` | Add a new glyph to the font. |
| `delete_glyph` | Remove a glyph from the font. |
| `update_glyph_properties` | Change unicode, category, export flags, etc. |
| `copy_glyph` | Duplicate outlines / components from one glyph to another. |
| `update_glyph_metrics` | Adjust width and side‑bearings. |
| `get_glyph_components` | Inspect components used in a glyph. |
| `add_component_to_glyph` | Append a component to a glyph layer. |
| `add_anchor_to_glyph` | Add an anchor to a glyph layer. |
| `set_kerning_pair` | Set or remove a kerning value. |
| `get_selected_glyphs` | Info about glyphs currently selected in UI. |
| `get_selected_font_and_master` | Current font + master and selection snapshot. |
| `get_selected_nodes` | Detailed selected nodes with per‑master mapping for edits. |
| `add_corner_to_all_masters` | Add a `_corner.*` corner hint at selected nodes (and intersection handles) across all masters (requires `_corner_name`). |
| `get_glyph_paths` | Export paths in a JSON format suitable for LLM editing. |
| `set_glyph_paths` | Replace glyph paths from JSON. |
| `ExportDesignspaceAndUFO` | Export designspace/UFO bundles with structured logs and errors. |
| `execute_code` | Execute arbitrary Python in the Glyphs context. |
| `execute_code_with_context` | Execute Python with injected helper objects. |
| `save_font` | Save the active font (optionally to a new path). |
| `docs_search` | Search bundled Glyphs SDK/ObjectWrapper docs by title/summary. |
| `docs_get` | Fetch a bundled docs page by id/path (supports paging via offset/max_chars). |

`execute_code` and `execute_code_with_context` accept an optional `timeout` in seconds. Calls default to 60 s, and the bridge honours any larger per-call value you provide.

For performance-sensitive scripts, you can opt into lower-overhead execution:
- `capture_output=false` to avoid capturing stdout/stderr (prints go to the Macro Panel).
- `return_last_expression=false` to skip evaluating the final line as an expression.
- `max_output_chars` / `max_error_chars` to cap returned output and avoid huge responses.

Avoid calling `exit()` / `quit()` / `sys.exit()` in `execute_code*`; they won't exit Glyphs and can disrupt the call.

### ExportDesignspaceAndUFO

Kick off a headless export of UFO masters and designspace documents directly from the MCP server. The tool returns absolute paths to generated files along with the exporter log so clients can surface progress in real time. Debug lines are prefixed with `[ExportDesignspaceAndUFO DEBUG]` and include helpful context about axis mappings, temporary folders, and file moves.

Failures now yield rich diagnostics instead of a bare string. In addition to `error`, the payload includes `errorType`, a formatted `traceback`, and contextual details about the font and options that triggered the exception. Use these fields to surface actionable feedback or drive automated retries without guessing what went wrong.

---

## Install & Setup

Recommended (simplest): run the one‑command interactive installer. It handles Python setup, dependencies, and placing the plug‑in where Glyphs expects it.

```bash
python3 install.py
```

Alternatively, you can install the plug‑in manually as described below.

## Install the Plug‑in

Copy or create a symlink of `src/glyphs-mcp/Glyphs MCP.glyphsPlugin` into
`~/Library/Application Support/Glyphs 3/Plugins/`, then restart Glyphs.

After regenerating the ObjectWrapper documentation, refresh the bundled copy with:

```bash
python src/glyphs-mcp/scripts/copy_documentation.py
```

To start the Glyphs MCP server, open the **Edit** menu and choose **Start MCP Server**.

The MCP endpoint is `http://127.0.0.1:9680/mcp/` using MCP Streamable HTTP transport.

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
Preferred: use `docs_search` + `docs_get` (on-demand). If you really want per-page resources, call `docs_enable_page_resources` (or set `GLYPHS_MCP_REGISTER_DOC_PAGES=1`).

## One‑Command Installer (Interactive)

Prefer a guided setup? Run the interactive installer to:
- choose Glyphs’ Python or a custom Python,
- install dependencies in the appropriate location, and
- copy the plug‑in into the Glyphs Plugins folder.

```bash
python3 install.py
```

### What the installer does

- Detects available Python 3 interpreters (prefers 3.12+, python.org builds).
- Installs Python dependencies either into Glyphs’ own Python or your user site‑packages.
- Installs the plug‑in into `~/Library/Application Support/Glyphs 3/Plugins/` by copy (recommended) or symlink (dev).
- Verifies imports and offers tips if something fails (e.g., Apple Silicon wheels, cache issues).

### Step‑by‑step flow and choices

1) Choose Python environment
   - Option 1: Glyphs’ Python (Plugin Manager)
     - Recommended default if you installed “Python” in Glyphs → Settings → Addons.
     - The installer uses Glyphs’ `pip` and installs into `~/Library/Application Support/Glyphs 3/Scripts/site-packages`.
     - If not found, it tells you to install “GlyphsPythonPlugin” in Glyphs and re‑run.
   - Option 2: Custom Python (python.org / Homebrew)
     - Recommended: python.org 3.12+ on macOS. On Apple Silicon, use native arm64 (avoid Rosetta).
     - The installer lists detected interpreters (python.org, Homebrew, PATH). Pick one or enter a path.
     - If version < 3.12, you’ll be warned and can abort to install a newer Python.

2) Install dependencies
   - Glyphs’ Python: installs with Glyphs’ `pip` into the Glyphs Scripts site‑packages.
   - Custom Python: runs `<python> -m pip install --user -r requirements.txt` (no sudo).
   - If imports fail, it suggests retrying with `--no-cache-dir --force-reinstall` and gives the exact command. On Apple Silicon, ensure wheels match the CPU architecture.

3) Install the plug‑in
   - Option 1: Copy (default, recommended)
     - Copies `src/glyphs-mcp/Glyphs MCP.glyphsPlugin` into `~/Library/Application Support/Glyphs 3/Plugins/`.
   - Option 2: Link (symlink; for development)
     - Useful if you plan to edit this repo and test changes live.
   - If a plug‑in already exists, you’ll be prompted to replace it.

4) Finish and start the server in Glyphs
   - Open Glyphs → Edit → Start MCP Server.
   - The MCP endpoint is `http://127.0.0.1:9680/mcp/` with MCP Streamable HTTP transport.
   - The installer can optionally show client setup snippets for popular tools (Claude Desktop, Claude Code, Continue, Cursor, Windsurf, Codex). It uses either `npx mcp-remote` or the Python `mcp-proxy` if on PATH.

Tips
- If you’re unsure, accept the defaults: “Glyphs’ Python” and “Copy”.
- Prefer python.org 3.12+ over Homebrew for fewer compatibility surprises on macOS.
- On Apple Silicon, avoid Rosetta‑translated Pythons and ensure `pip` installs arm64 wheels.
- No sudo is required; everything installs into your user directories.

Endpoint check
- Browser `GET` requests to `/mcp/` return a small JSON discovery payload.
- Verify locally: `curl -H 'Accept: application/json' http://127.0.0.1:9680/mcp/`

## Build Site Images (WebP)

Docs use a splash image at `/images/glyphs-app-mcp/glyphs-mcp.webp`.

- Requirements: Node 20+ and the `sharp` package (`npm i sharp`).
- Convert PNG assets from `content/images/glyphs-app-mcp` to WebP in `public/images/glyphs-app-mcp`:

```bash
node scripts/convert-images.mjs
```

The script ensures `glyphs-mcp.webp` (the hero image for the doc) is generated, then converts the rest.

---

## Build Release ZIP (Clean)

To package the plug‑in for distribution without accidentally shipping local artifacts (`__pycache__`, `.pyc`, `.venv`, `__MACOSX`, etc.), use:

```bash
./scripts/build_release_zip.sh
```

Optionally override the version label used in the filename:

```bash
./scripts/build_release_zip.sh --version 1.0.0
```

The ZIP is written to `dist/` (ignored by git).

## Contributing
PRs and feedback are welcome.

### Contributors
- Thierry Charbonnel (@thierryc) — Author
- Florian Pircher (@florianpircher)
- Georg Seifert (@schriftgestalt)
- Jeremy Tribby (@jpt)

---

 
