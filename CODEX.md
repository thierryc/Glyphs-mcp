# CODEX.md

This briefing gives the Codex CLI agent the context needed to work on Glyphs MCP.

## Mission Brief
- Glyphs MCP is a Python-based MCP server packaged as a Glyphs 3 plugin.
- The server exposes GlyphsApp functionality as JSON-RPC tools via Streamable HTTP at `http://127.0.0.1:9680/mcp/`.
- Dependencies are vendored into the plugin bundle (`Contents/Resources/vendor/`) for zero-config installation.

## Repository Map
- `src/glyphs-mcp/` — Core plugin code, MCP tool implementations, and build scripts.
- `Documentations/` — Generated docs copied into the plugin by `copy_documentation.py`.
- `glyphs-build-env/` — Optional local virtual environment for development tooling.
- `README.md` — Current tool catalog, build steps, and IDE connection examples.

## Everyday Commands
- **Install/update plugin:** `python3 install.py` (vendors deps and symlinks plugin)
- **Rebuild vendored deps:** `python3.XX src/glyphs-mcp/scripts/vendor_deps.py` (use the Python version you want to target: 3.11, 3.12, 3.13, or 3.14)
- **Update requirements:** `uv pip compile pyproject.toml --python-version 3.11 --upgrade -o requirements.txt`
- **Sync ObjectWrapper docs:** `python src/glyphs-mcp/scripts/copy_documentation.py`
- **Start the server:** Restart Glyphs, then **Edit → Start MCP Server**

## MCP Tool Surface (selected)
- Metadata: `list_open_fonts`, `get_font_glyphs`, `get_font_masters`, `get_font_instances`.
- Glyph inspection: `get_glyph_details`, `get_glyph_paths`, `get_glyph_components`, `get_selected_glyphs`, `get_selected_nodes`.
- Editing: `create_glyph`, `delete_glyph`, `copy_glyph`, `add_component_to_glyph`, `add_anchor_to_glyph`, `set_glyph_paths`.
- Metrics & persistence: `update_glyph_metrics`, `update_glyph_properties`, `set_kerning_pair`, `save_font`.
- Automation: `execute_code`, `execute_code_with_context`, `get_selected_font_and_master`.

Refer to `README.md` for the full command table and usage notes.

## Agent Guidelines
- Prefer `rg`/`fd` style tools for repo searches; avoid altering the plugin
  bundle directly unless necessary.
- Keep documentation ASCII-only unless the file already uses other characters.
- When adding tooling, update both the README table and relevant agent guides (Claude/Codex).
- After changes that touch the plugin bundle, remind users to reinstall or resymlink it into the Glyphs plugins directory.
