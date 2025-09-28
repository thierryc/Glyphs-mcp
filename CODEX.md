# CODEX.md

This briefing gives the Codex CLI agent the context needed to work on Glyphs MCP.

## Mission Brief
- Glyphs MCP is a Python-based MCP server packaged as a Glyphs 3 plugin.
- The server exposes GlyphsApp functionality as JSON-RPC tools via Streamable HTTP at `http://127.0.0.1:9680/mcp/`.
- Dependencies are vendored into the plugin bundle inside `src/glyphs-mcp/Glyphs MCP.glyphsPlugin`.

## Repository Map
- `src/glyphs-mcp/` — Core plugin code, MCP tool implementations, and build scripts.
- `Documentations/` — Generated docs copied into the plugin by `copy_documentation.py`.
- `glyphs-build-env/` — Virtual environment used when bundling third-party packages.
- `README.md` — Current tool catalog, build steps, and IDE connection examples.

## Everyday Commands
- Activate tooling env: `source glyphs-build-env/bin/activate`.
- Refresh vendored libraries: `src/glyphs-mcp/scripts/vendor_deps.sh`.
- Sync ObjectWrapper docs into the plugin: `python src/glyphs-mcp/scripts/copy_documentation.py`.
- Start the server from Glyphs: restart the app, then **Edit → Start MCP Server**.

## MCP Tool Surface (selected)
- Metadata: `list_open_fonts`, `get_font_glyphs`, `get_font_masters`, `get_font_instances`.
- Glyph inspection: `get_glyph_details`, `get_glyph_paths`, `get_glyph_components`, `get_selected_glyphs`.
- Editing: `create_glyph`, `delete_glyph`, `copy_glyph`, `add_component_to_glyph`, `add_anchor_to_glyph`, `set_glyph_paths`.
- Metrics & persistence: `update_glyph_metrics`, `update_glyph_properties`, `set_kerning_pair`, `save_font`.
- Automation: `execute_code`, `execute_code_with_context`, `get_selected_font_and_master`.

Refer to `README.md` for the full command table and usage notes.

## Agent Guidelines
- Prefer `rg`/`fd` style tools for repo searches; avoid altering vendored bundles unless necessary.
- Keep documentation ASCII-only unless the file already uses other characters.
- When adding tooling, update both the README table and relevant agent guides (Claude/Codex).
- After changes that touch the plugin bundle, remind users to reinstall or resymlink it into the Glyphs plugins directory.

