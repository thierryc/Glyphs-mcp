# CODEX.md

This briefing gives the Codex CLI agent the context needed to work on Glyphs MCP.

## Mission Brief
- Glyphs MCP is a Python-based MCP server packaged as a Glyphs 3 plugin.
- The server exposes GlyphsApp functionality as JSON-RPC tools via Streamable HTTP at `http://127.0.0.1:9680/mcp/`.
- A plain browser `GET` to `/mcp/` returns JSON discovery; MCP clients connect using SSE (`Accept: text/event-stream`).
- Dependencies are installed into the user Scripts `site-packages` directory,
  not vendored inside the plugin.
- Resources are helper reference material (guide + docs) to improve tool calls and generated code.

## Repository Map
- `src/glyphs-mcp/` — Core plugin code, MCP tool implementations, and build scripts.
- `Documentations/` — Generated docs copied into the plugin by `copy_documentation.py`.
- `glyphs-build-env/` — Optional local virtual environment for development tooling.
- `README.md` — Current tool catalog, build steps, and IDE connection examples.

## Everyday Commands
- Activate tooling env: `source glyphs-build-env/bin/activate`.
- Install dependencies:
  - `src/glyphs-mcp/scripts/install_deps_glyphs_python.sh` (Glyphs’ Python → installs into `~/Library/Application Support/Glyphs 3/Scripts/site-packages`)
  - `src/glyphs-mcp/scripts/install_deps_external_python.sh` (external Python → installs into that Python’s user site-packages)
- Sync ObjectWrapper docs into the plugin: `python src/glyphs-mcp/scripts/copy_documentation.py`.
- Start the server from Glyphs: restart the app, then **Edit → Start MCP Server**.

## MCP Tool Surface (selected)
- Metadata: `list_open_fonts`, `get_font_glyphs`, `get_font_masters`, `get_font_instances`.
- Glyph inspection: `get_glyph_details`, `get_glyph_paths`, `get_glyph_components`, `get_selected_glyphs`, `get_selected_nodes`.
- Editing: `create_glyph`, `delete_glyph`, `copy_glyph`, `add_component_to_glyph`, `add_anchor_to_glyph`, `set_glyph_paths`.
- Metrics & persistence: `update_glyph_metrics`, `update_glyph_properties`, `set_kerning_pair`, `save_font`.
- Automation: `execute_code`, `execute_code_with_context`, `get_selected_font_and_master`.
- Docs helpers: `docs_search`, `docs_get`.

## Helper Resources
- Guide: `glyphs://glyphs-mcp/guide`
- Docs index: `glyphs://glyphs-mcp/docs/index.json`

Refer to `README.md` for the full command table and usage notes.

## Agent Execution Contract (Guide-Aligned)
- Read current state before mutation (`get_selected_font_and_master`, `get_selected_glyphs`, `get_glyph_details`/`get_glyph_paths` as needed).
- Prefer dedicated mutation tools first; use `execute_code_with_context` or `execute_code` for multi-step workflows where one script is more reliable.
- For `execute_code*`, keep scripts minimal, validate targets first, and bound output with `max_output_chars` / `max_error_chars` when needed.
- After each mutation, re-read affected entities and report changed/skipped counts.

## Agent Guidelines
- Prefer `rg`/`fd` style tools for repo searches; avoid altering the plugin
  bundle directly unless necessary.
- Keep documentation ASCII-only unless the file already uses other characters.
- When adding tooling, update both the README table and relevant agent guides (Claude/Codex).
- After changes that touch the plugin bundle, remind users to reinstall or resymlink it into the Glyphs plugins directory.
