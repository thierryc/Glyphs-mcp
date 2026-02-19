# Glyphs MCP
![Glyphs MCP splash](/content/images/glyphs-app-mcp/glyphs-mcp.webp)

A Machine-Control-Protocol server for [Glyphs](https://glyphsapp.com) that exposes font-specific tools to AI and LLM agents.

---

## What is an MCP server?
A *Model Context Protocol* server is a lightweight process that:

1. **Registers tools** (JSON-RPC methods) written in the host language (Python here).
2. **Streams JSON output** back to the calling agent.

Bridging Glyphs with MCP makes it possible for assistants to read, inspect, and manipulate Glyphs documents in the same way a human operator would.

---

## Table of contents
- [Command set (server v1.0.0)](#command-set-server-v1-0-0)
- [Client setup](#client-setup)
  - [OpenAI Codex CLI](#openai-codex-cli)
  - [Claude Desktop](#claude-desktop)
  - [Cursor IDE](#cursor-ide)
  - [Windsurf](#windsurf)
  - [Claude Code (VS Code)](#claude-code-vs-code)
  - [Continue (VS Code / JetBrains)](#continue-vs-code-jetbrains)
- [Access & contributing](#access-contributing)
- [Build the Glyphs plug-in](#build-the-glyphs-plug-in)

---

## Command set (server v1.0.0)

Command table for the MCP server version exposed in code (FastMCP `version="1.0.0"`).
| Tool | Description |
|------|-------------|
| `list_open_fonts` | List all open fonts and basic metadata. |
| `get_font_glyphs` | Return glyph list and key attributes for a font. |
| `get_font_masters` | Detailed master information for a font. |
| `get_font_instances` | List instances and their interpolation data. |
| `get_glyph_details` | Full glyph data including layers, paths, components. |
| `get_font_kerning` | All kerning pairs for a given master. |
| `generate_kerning_tab` | Generate a kerning review proof tab (missing relevant pairs + outliers) and open it. |
| `review_kerning_bumper` | Review kerning collisions / near-misses and compute deterministic “bumper” suggestions (no mutation). |
| `apply_kerning_bumper` | Apply “bumper” suggestions as glyph–glyph kerning exceptions (supports `dry_run`; requires `confirm=true` to mutate). |
| `create_glyph` | Add a new glyph to the font. |
| `delete_glyph` | Remove a glyph from the font. |
| `update_glyph_properties` | Change unicode, category, export flags, etc. |
| `copy_glyph` | Duplicate outlines or components from one glyph to another. |
| `update_glyph_metrics` | Adjust width and side-bearings. |
| `review_spacing` | Review spacing and suggest sidebearings/width (area-based; no mutation). |
| `apply_spacing` | Apply spacing suggestions (supports `dry_run`; requires `confirm=true` to mutate). |
| `set_spacing_params` | Set spacing parameters as font/master custom parameters (no auto-save). |
| `set_spacing_guides` | Add or clear glyph-level guides visualizing the spacing measurement band (no auto-save). |
| `get_glyph_components` | Inspect components used in a glyph. |
| `add_component_to_glyph` | Append a component to a glyph layer. |
| `add_anchor_to_glyph` | Add an anchor to a glyph layer. |
| `set_kerning_pair` | Set or remove a kerning value. |
| `get_selected_glyphs` | Info about glyphs currently selected in UI. |
| `get_selected_font_and_master` | Current font + master and selection snapshot. |
| `get_selected_nodes` | Detailed selected nodes with per-master mapping for edits. |
| `add_corner_to_all_masters` | Add a `_corner.*` corner hint at selected nodes (and intersection handles) across all masters (requires `_corner_name`; optional `_alignment`: `left`/`right`/`center` or `0`/`1`/`2`). |
| `get_glyph_paths` | Export paths in a JSON format suitable for LLM editing. |
| `set_glyph_paths` | Replace glyph paths from JSON. |
| `ExportDesignspaceAndUFO` | Export designspace/UFO bundles with structured logs and errors. |
| `execute_code` | Execute arbitrary Python in the Glyphs context. |
| `execute_code_with_context` | Execute Python with injected helper objects. |
| `save_font` | Save the active font (optionally to a new path). |
| `docs_search` | Search bundled Glyphs SDK/ObjectWrapper docs by title/summary. |
| `docs_get` | Fetch a bundled docs page by id/path (supports paging via offset/max_chars). |

`execute_code` and `execute_code_with_context` accept an optional `timeout` in seconds. Each call defaults to 60 s, and the bridge honours any larger per-call value that you include in the tool arguments.

For performance-sensitive scripts, you can opt into lower-overhead execution:
- `capture_output=false` to avoid capturing stdout/stderr (prints go to the Macro Panel).
- `return_last_expression=false` to skip evaluating the final line as an expression.
- `max_output_chars` / `max_error_chars` to cap returned output and avoid huge responses.

Avoid calling `exit()` / `quit()` / `sys.exit()` in `execute_code*`; they won't exit Glyphs and can disrupt the call.

### Kerning review: `generate_kerning_tab`

`generate_kerning_tab` opens a new Edit tab in Glyphs containing kerning proof text. It is designed to help you:

1) **Kern what matters next**: a worklist of missing high‑relevance pairs (based on a bundled snapshot of Andre Fuchs’ relevance-ranked kerning pairs dataset; MIT).
2) **Audit outliers**: your master’s tightest and widest existing explicit kerning values (often where rhythm breaks).

The tool does **not** change kerning values. It only reads kerning + glyph metadata, generates a proof string, and opens a tab.

For an end‑to‑end kerning checklist + LLM prompt pack (aligned with Glyphs’ kerning workflow), see `content/kerning-workflow.md`.

#### Prompt templates (copy/paste)

> Note: tool name prefixes vary by client. If your tools aren’t named `glyphs-app-mcp__*`, replace that prefix with whatever your MCP client shows.

**Default (worklist + outliers, opens a tab)**
```text
In Glyphs, generate a kerning review tab for my current font/master.

1) Call glyphs-app-mcp__generate_kerning_tab with:
{"font_index":0,"rendering":"hybrid"}

2) After it returns:
- Tell me the counts + any warnings.
- Explain what each section in the tab is for.
- Extract the first 25 missing pairs from the “MISSING RELEVANT PAIRS” section and tell me which 10 you’d kern first (class-first).
```

**Focus on specific glyphs**
```text
Generate a kerning review tab focusing only on these glyphs: A V W Y T o a e comma period quotedblleft quotedblright.

Call glyphs-app-mcp__generate_kerning_tab:
{"font_index":0,"glyph_names":["A","V","W","Y","T","o","a","e","comma","period","quotedblleft","quotedblright"],"rendering":"hybrid","missing_limit":300,"audit_limit":100}

Then summarize counts and list the top missing pairs to kern first.
```

**Audit-only (no “missing” section)**
```text
Open a kerning audit tab showing only the tightest and widest existing explicit kerning pairs (no missing-pairs worklist).

Call glyphs-app-mcp__generate_kerning_tab:
{"font_index":0,"missing_limit":0,"audit_limit":250,"rendering":"hybrid"}

Then summarize the most extreme values and what they likely indicate.
```

### Kerning collision guard: `review_kerning_bumper` / `apply_kerning_bumper`

These tools add a **geometry-based guardrail** for kerning:
- Measure a pair’s **minimum outline gap** across the glyphs’ **vertical overlap** (band-by-band).
- Flag **collisions / near-misses** under a configurable `min_gap`.
- Propose a deterministic **“bumper” loosening**: the minimum kerning increase needed to meet the gap constraint.

This is not “optical kerning”. It’s a clean-room collision detector + safety suggestion engine.

`review_kerning_bumper` does **not** mutate kerning.  
`apply_kerning_bumper` writes **glyph–glyph exceptions only** (never class kerning) and is confirm-gated.

For a full deep-dive, see `content/kerning-tools.md`.
For an end‑to‑end kerning checklist + tutorial, see `content/kerning-workflow.md`.

#### Prompt templates (copy/paste)

> Note: tool name prefixes vary by client. If your tools aren’t named `glyphs-app-mcp__*`, replace that prefix with whatever your MCP client shows.

**Review collisions (no mutation)**
```text
In Glyphs, review kerning collisions for my current font/master and propose safe bumper values.

1) Call glyphs-app-mcp__review_kerning_bumper:
{"font_index":0,"min_gap":5,"relevant_limit":2000,"include_existing":true,"scan_mode":"two_pass","dense_step":10,"bands":8}

2) Summarize:
- How many pairs were measured vs skipped (and why)
- The 20 worst collisions (lowest minGap) and their recommendedException values
- Any warnings about dataset size or scan settings
```

**Open a proof tab for the worst collisions**
```text
Open a kerning collision proof tab for the worst pairs, then tell me what to kern first.

Call glyphs-app-mcp__review_kerning_bumper:
{"font_index":0,"min_gap":5,"open_tab":true,"result_limit":120,"rendering":"hybrid","per_line":12}
```

**Apply bumpers safely (dry run → confirm)**
```text
I want you to fix collisions by adding glyph–glyph kerning exceptions only.
Rules:
- Never auto-save.
- Never mutate without a dry run first.
- Only loosen (never tighten).

1) Call glyphs-app-mcp__apply_kerning_bumper (dry run):
{"font_index":0,"dry_run":true,"min_gap":5,"extra_gap":0,"max_delta":200,"relevant_limit":2000,"include_existing":true}

2) Show me the first 50 proposed changes (old → new) and the biggest deltas.
3) If I say “apply”, call apply_kerning_bumper again with confirm=true using the same args.
4) If I say “re-proof”, call glyphs-app-mcp__review_kerning_bumper with open_tab=true.
5) If I say “save”, call glyphs-app-mcp__save_font.
```

### Spacing workflow: `review_spacing` / `apply_spacing` (HTspacer-style)

The spacing tools focus on **sidebearings first** (rhythm and consistency), before you sink time into kerning.

- `review_spacing` suggests LSB/RSB/width changes (no mutation).
- `apply_spacing` applies the same suggestions (requires `dry_run=true` or `confirm=true`).
- Nothing auto-saves; call `save_font` when you’re happy.

For a deeper reference (defaults, rules, clamping, and guides), see `content/spacing-tools.md`.

#### Prompt templates (copy/paste)

> Note: tool name prefixes vary by client. If your tools aren’t named `glyphs-app-mcp__*`, replace that prefix with whatever your MCP client shows.

**Default spacing pass (review → dry-run → apply)**
```text
You are my spacing assistant for a Glyphs font.
Rules:
- Never auto-save.
- Never mutate without a dry run first.
- Keep changes conservative (use clamping).

Task: Improve spacing consistency for my current selection in the active font.

1) Call glyphs-app-mcp__review_spacing:
{"font_index":0}

2) Summarize the top spacing outliers and skip reasons.

3) Call glyphs-app-mcp__apply_spacing (dry run):
{"font_index":0,"dry_run":true,"clamp":{"maxDeltaLSB":80,"maxDeltaRSB":80,"minLSB":-50,"minRSB":-50}}

4) If I say “apply”, call apply_spacing again with confirm=true using the same clamp.
5) If I say “save”, call glyphs-app-mcp__save_font.
```

**Tabular figures pass (fixed width)**
```text
I want tabular figures to keep a fixed width by distributing width changes evenly across LSB/RSB.
Select your figure glyphs in Glyphs first, then:

1) Call glyphs-app-mcp__review_spacing:
{"font_index":0,"defaults":{"tabularMode":true,"tabularWidth":600,"referenceGlyph":"zero"}}

2) Call glyphs-app-mcp__apply_spacing (dry run):
{"font_index":0,"dry_run":true,"defaults":{"tabularMode":true,"tabularWidth":600,"referenceGlyph":"zero"},"clamp":{"maxDeltaLSB":60,"maxDeltaRSB":60,"minLSB":-50,"minRSB":-50}}

3) If I approve, call apply_spacing again with confirm=true using the same args.
```

### Using `get_selected_nodes`

`get_selected_nodes` returns actionable details about the current selection in Edit View, including per‑master mapping hints. The structure is designed so an agent can perform follow‑up edits (e.g., insert a point before the selected node) on all masters of the same glyph.

- Node fields: `pathIndex`, `nodeIndex`, `nodeType`, `smooth`, `position {x,y}`, `closed`
- Topology hints: `onCurveIndex`, `segment` (neighbor indices and off‑curve ordinal), `pathSignature`
- Cross‑master mapping: `mapping[]` with `masterId`, `pathIndex`, `nodeIndex`, `onCurveIndex`

Example follow-up (conceptual): fetch selection, then insert a midpoint node before each mapped node across masters using `execute_code` or `execute_code_with_context`.

### ExportDesignspaceAndUFO

Run a full designspace/UFO export cycle from the MCP client without touching the UI. The tool returns absolute paths for generated designspace files, master UFOs, brace UFOs, and support scripts together with the exporter log so agents can stream progress back to the user. Debug messages are prefixed with `[ExportDesignspaceAndUFO DEBUG]` and surface context such as detected axes, temporary directories, and file moves.

When something goes wrong the response includes diagnostics beyond a plain string. The error payload adds `errorType`, a formatted `traceback`, and contextual metadata so you can report actionable feedback or retry with adjusted options. Example failure response:

```json
{
  "error": "Axis 'Width' missing mapping for coordinate KeyError(10.0)",
  "errorType": "KeyError",
  "traceback": ["Traceback (most recent call last):", "  ..."],
  "font": {"familyName": "Example Sans", "filePath": "/Users/example/fonts/example-sans.glyphs"},
  "options": {"include_variable": true, "include_static": true, "brace_layers_mode": "layers", "include_build_script": true, "output_directory": "/tmp/build"},
  "log": [
    "Building designspace from font metadata (static).",
    "[ExportDesignspaceAndUFO DEBUG] Axis 'Width' uses custom Axis Mapping keys: [75.0, 100.0, 125.0]"
  ]
}
```

Successful runs set `success: true` and mirror the same `log` array so clients always have insight into exporter activity.

---

## Resources (helpers)

The server is tools-first. Resources exist to help the assistant write better GlyphsApp code with fewer mistakes.

- Guide: `glyphs://glyphs-mcp/guide`
- Docs directory listing: `glyphs://glyphs-mcp/docs`
- Docs index: `glyphs://glyphs-mcp/docs/index.json`
- Kerning datasets listing: `glyphs://glyphs-mcp/kerning`
- Andre Fuchs relevant pairs (normalized snapshot): `glyphs://glyphs-mcp/kerning/andre-fuchs/relevant_pairs.v1.json`

By default, individual doc pages are not registered as separate resources (to avoid flooding MCP clients). Prefer `docs_search` + `docs_get` (on-demand). If you really want per-page resources, call `docs_enable_page_resources` (or set `GLYPHS_MCP_REGISTER_DOC_PAGES=1`).

## Client setup
Configure your preferred AI client to speak the Streamable HTTP endpoint. Below are quick-start snippets for common tools.

Note: `http://127.0.0.1:9680/mcp/` is an SSE endpoint for MCP clients. If you open it in a browser, it returns a small JSON discovery response instead.

Tip: If your coding agent doesn't connect to the running Glyphs app, launch Glyphs fresh and start the MCP server first (Edit → Start Glyphs MCP Server, or enable auto-start in Edit → Glyphs MCP Server Status…). Then start the coding agent (Claude, Codex, etc.) after.

### OpenAI Codex CLI
![OpenAI Codex MCP configuration screenshot](/content/images/glyphs-app-mcp/codex-in-vs-code.webp)
![OpenAI Codex result screenshot](/content/images/glyphs-app-mcp/codex-result-in-vs-code.webp)

Codex understands MCP servers via `codex mcp` helpers. For a local Streamable HTTP server like Glyphs MCP, you can connect directly by URL (no Node required). Add the configuration to `~/.codex/config.toml`, then restart any active Codex sessions.

```toml
[mcp_servers.glyphs-mcp-server]
url = "http://127.0.0.1:9680/mcp/"
enabled = true
startup_timeout_sec = 30
tool_timeout_sec = 120
```

If you prefer to bridge the connection through `mcp-remote` (for example to share a single configuration across tools), you can keep the proxy-based setup. This requires Node 20+:

```toml
[mcp_servers.glyphs-mcp-server]
command = "npx"
args = ["--yes", "mcp-remote", "http://127.0.0.1:9680/mcp/"]
```

You can run `codex config path` to verify the location if you've customised the CLI setup.

### Claude Desktop
![Claude Desktop MCP registry screenshot](/content/images/glyphs-app-mcp/claude-sonnet.webp)

Claude Desktop reads configuration from `/Users/<userName>/Library/Application Support/Claude/claude_desktop_config.json`. Append the server definition and restart the app:

```json
{
  "globalShortcut": "Alt+Ctrl+Cmd+*",
  "mcpServers": {
    "glyphs-mcp-server": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://127.0.0.1:9680/mcp/"
      ],
      "env": {
        "PATH": "/Users/yourUserName/.nvm/versions/node/v22.19.0/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
      }
    }
  }
}
```

Claude Desktop spawns MCP servers without your interactive shell profile, and its bundled Node runtime is typically older than v20. Because `mcp-remote` itself targets Node 20+, the explicit `PATH` entry forces `npx` to resolve to your local Node 22 installation so the CLI boots successfully.

Prefer Python tooling instead of Node? Install the proxy from PyPI and point Claude directly at the Python binary:

```bash
pip3 install --user mcp-proxy
# upgrade later with: python3.12 -m pip install --user --upgrade mcp-proxy
```

```json
{
  "globalShortcut": "Alt+Ctrl+Cmd+*",
  "mcpServers": {
    "glyphs-mcp-server": {
      "command": "/Library/Frameworks/Python.framework/Versions/3.12/bin/mcp-proxy",
      "args": [
        "--transport",
        "streamablehttp",
        "http://127.0.0.1:9680/mcp/"
      ],
      "env": {
        "PATH": "/Library/Frameworks/Python.framework/Versions/3.12/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
      }
    }
  }
}
```

Claude Desktop still discards your login shell. The explicit `PATH` entry ensures the app finds the `mcp-proxy` shim that `pip3` drops into Python 3.12’s `bin` directory before falling back to the system defaults. If your Python lives elsewhere (for example a `pyenv` or Homebrew install), replace `/Library/Frameworks/Python.framework/Versions/3.12/bin` with the result of `python3 -m site --user-base` plus `/bin`.

### Cursor IDE
![Cursor MCP configuration screenshot](/content/images/glyphs-app-mcp/cursor-gemini.webp)

Cursor stores its MCP registry in `~/.cursor/mcp.json`. Drop in the JSON below to wire up the Glyphs server—the `PATH` override makes sure `npx` resolves to your Node 20+ install so `mcp-remote` can launch:

```json
{
  "mcpServers": {
    "glyphs-mcp-server": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://127.0.0.1:9680/mcp/"
      ],
      "env": {
        "PATH": "/Users/yourUserName/.nvm/versions/node/v22.19.0/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
      }
    }
  }
}
```

Cursor still honours the legacy YAML file if you prefer that format:

```yaml
mcpServers:
  - name: glyphs-mcp
    type: streamable-http
    url: http://127.0.0.1:9680/mcp/
```

### Windsurf
![Windsurf MCP integration screenshot](/content/images/glyphs-app-mcp/windsurf.webp)
![Windsurf MCP configuration screenshot](/content/images/glyphs-app-mcp/windsurf-config.webp)

Windsurf reads MCP configuration from `~/.codeium/windsurf/mcp_config.json`. Use the streamlined serverUrl format:

```json
{
  "mcpServers": {
    "glyphs-mcp-server": {
      "serverUrl": "http://127.0.0.1:9680/mcp/"
    }
  }
}
```

### Claude Code (VS Code)
Use the Claude CLI to register the MCP server directly. The VS Code extension will discover it automatically:

```bash
claude mcp add --transport http glyphs-mcp-server http://127.0.0.1:9680/mcp/
```

After adding, reload VS Code (or the Claude extension) if it’s already running.

### Continue (VS Code / JetBrains)
![Continue MCP configuration screenshot](/content/images/glyphs-app-mcp/continue-in-vs-code.webp)

Continue supports MCP through YAML configuration. Drop the snippet below into `~/.continue/config.yaml` (or a workspace override):

```yaml
mcpServers:
  - name: Glyphs MCP
    # Local MCP server using Streamable HTTP transport
    type: streamable-http
    url: http://127.0.0.1:9680/mcp/
```

To scope the server to a single project, create a workspace override at `./.continue/config.yaml` in your repository:

```yaml
name: New MCP server
version: 0.0.1
schema: v1
mcpServers:
  - name: Glyphs MCP
    # Local MCP server using Streamable HTTP transport
    type: streamable-http
    url: http://127.0.0.1:9680/mcp/
```

If you start Continue before launching Glyphs, open the MCP submenu inside the Continue sidebar and click **Reload** so the editor picks up the freshly started server.

#### VS Code discovery shortcut
If you prefer to let VS Code auto-discover MCP servers registered by Claude Desktop, Cursor, or other tools, flip on the built-in discovery toggle via `vscode://settings/chat.mcp.discovery.enabled`. Once the setting is enabled, restart the chat session and the `glyphs-mcp-server` entry should appear without manual YAML edits.

---

## Access & contributing
PRs, test reports, and ideas are always welcome. The semi-private repository lives at [github.com/thierryc/Glyphs-mcp](https://github.com/thierryc/Glyphs-mcp). Send a direct message on the Glyphs Forum to unlock access: [Exploring the role of AI in typeface design](https://forum.glyphsapp.com/t/exploring-the-role-of-ai-in-typeface-design-with-glyphs/33343/63).

Questions? Say hello at [thierry@anotherplanet.io](mailto:thierry@anotherplanet.io) or [@anotherplanet_io](https://www.instagram.com/anotherplanet_io/). When you are done, head back [home](/) for the full portfolio.

---

## Install the plug‑in

### One-command installer (recommended)
From the repo root, run the guided interactive installer:

```bash
python3 install.py
```

Supported Python versions: 3.11–3.13. The installer warns (and lets you abort) when selecting older Pythons, and blocks Python 3.14+ until tested.

On macOS, you can also double‑click `RunInstall.command` in Finder to launch the same installer. If Gatekeeper blocks it, right‑click → Open once to approve.

### Manual install (fallback)
If you prefer to do it by hand (or you are troubleshooting / developing), follow the steps below.

Copy or symlink `src/glyphs-mcp/Glyphs MCP.glyphsPlugin` into `~/Library/Application Support/Glyphs 3/Plugins/`, then restart Glyphs.

If you regenerate the ObjectWrapper documentation, refresh the bundled copy with:

```bash
python src/glyphs-mcp/scripts/copy_documentation.py
```

Once installed, open Glyphs and choose **Edit → Start Glyphs MCP Server**. The service listens on `http://127.0.0.1:9680/mcp/` using the MCP Streamable HTTP transport. Open the **Macro Panel** to monitor console output.

---

## Install dependencies
If you used the installer above, it already handled dependencies. Manual steps below are a fallback.

Dependencies are no longer bundled inside the plug‑in. Install them into your user Scripts site‑packages so Glyphs can import them.

### Option A: Use Glyphs’ Python (default)
If you use the Python that Glyphs installs via the Plugin Manager:

```bash
GLYPHS_BASE="$HOME/Library/Application Support/Glyphs 3"
PYTHON_BASE="$GLYPHS_BASE/Repositories/GlyphsPythonPlugin/Python.framework"
"$PYTHON_BASE/Versions/Current/bin/pip3" install \
  --target="$GLYPHS_BASE/Scripts/site-packages" \
  -r requirements.txt
```

Or run:

```bash
src/glyphs-mcp/scripts/install_deps_glyphs_python.sh
```

### Option B: Use another Python (e.g. python.org or Homebrew)
We recommend Python 3.12 from python.org:

```bash
PYTHON="/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12"
"$PYTHON" -m pip install --user -r requirements.txt
```

Or run the helper script (auto-detects Python 3.12 if available):

```bash
src/glyphs-mcp/scripts/install_deps_external_python.sh \
  --python /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
```

Restart Glyphs after installing dependencies.
