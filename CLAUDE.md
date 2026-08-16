# CLAUDE.md

This guide briefs Claude Code on how to work with the Glyphs MCP repository.

## Project Overview
- Glyphs MCP is a Model Context Protocol (MCP) server bundled as a Glyphs 3 plugin.
- It exposes GlyphsApp APIs as JSON-RPC tools over the MCP Streamable HTTP transport.
- Python sources live in `src/glyphs-mcp/`; dependencies install into the user
  Scripts `site-packages` directory (not vendored into the plugin).

## Capabilities Exposed to Agents
The shipped tool set focuses on glyph inspection, editing, and project metadata:
- `list_open_fonts`, `get_font_masters`, `get_font_instances` for font-level information.
- `get_glyph_details`, `get_glyph_paths`, `get_glyph_components`, `get_selected_glyphs` for glyph structure.
- `create_glyph`, `delete_glyph`, `copy_glyph`, `add_component_to_glyph`, `add_anchor_to_glyph` for building glyphs.
- `update_glyph_metrics`, `update_glyph_properties`, `set_kerning_pair`, `save_font` for metrics and persistence.
- `execute_code`, `execute_code_with_context`, `get_selected_font_and_master` for scripted automation inside Glyphs.
- `docs_search`, `docs_get` for on-demand access to bundled SDK/ObjectWrapper docs.

Refer to `README.md` for the complete table of supported tools and descriptions.

## Repository Layout Highlights
- `src/glyphs-mcp/` — MCP implementation, plugin bundle, and helper scripts.
- `src/glyphs-mcp-v2/` — Isolated, unreleased 2.0 typed runtime foundation on `lit/v2`.
- `Documentations/` — Generated ObjectWrapper docs that get copied into the plugin.
- `glyphs-build-env/` — Optional local virtual environment for development tooling.
- `README.md` — High-level overview, tool catalog, and IDE configuration snippets.

## Build & Run Workflow
1. Install dependencies using one option:
   - `src/glyphs-mcp/scripts/install_deps_glyphs_python.sh` (uses Glyphs’ Python → installs into `~/Library/Application Support/Glyphs 3/Scripts/site-packages`), or
   - `src/glyphs-mcp/scripts/install_deps_external_python.sh` (uses external Python → installs into that Python’s user site-packages)
2. Copy or symlink `src/glyphs-mcp/Glyphs MCP.glyphsPlugin` into `~/Library/Application Support/Glyphs 3/Plugins/`.
3. Restart Glyphs, then choose **Edit → Start MCP Server**. The server listens on `http://127.0.0.1:9680/mcp/` using Streamable HTTP.

After regenerating ObjectWrapper documentation, update the bundled copy with:

```
python src/glyphs-mcp/scripts/copy_documentation.py
```

The v2 foundation remains separate from the installed 1.x plug-in. Run its
tests through the repository suite and assemble its two deterministic payload
layouts without installing them:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_BIN=python3.12 ./scripts/run_python_tests.sh
python3.12 scripts/build_v2_runtime_payload.py
```

Keep v2 environments and generated state inside `.venv-v2/`, `.cache/v2/`,
`build/`, and `dist/` in this worktree.

## Security & Transport Notes
- The server binds locally starting at port 9680; keep it on loopback during development.
- Responses stream via MCP Streamable HTTP (SSE under the hood); preserve any `Mcp-Session-Id` header returned by the server.
- If you open `http://127.0.0.1:9680/mcp/` in a browser, the server returns a JSON discovery payload; MCP clients should connect with `Accept: text/event-stream`.
- Add authentication (for example bearer tokens) before exposing the transport beyond localhost.

## Helper Resources
- Guide: `glyphs://glyphs-mcp/guide`
- Docs index: `glyphs://glyphs-mcp/docs/index.json`

## Agent Execution Contract (Guide-Aligned)
- Read context before any mutation (`get_selected_font_and_master`, `get_selected_glyphs`, plus glyph detail/path reads as required).
- Prefer dedicated tools first; use `execute_code_with_context` or `execute_code` early for complex multi-step workflows when one scripted pass is more reliable.
- In `execute_code*`, validate targets before edits, keep scripts focused, and cap output with `max_output_chars` / `max_error_chars` when needed.
- Verify by reading back and report changed/skipped counts and unresolved risks.

## Client Configuration
Use direct HTTP clients for local setup. The recommended commands are:

```bash
codex mcp add glyphs-mcp-server --url http://127.0.0.1:9680/mcp/
```

```bash
claude mcp add --scope user --transport http glyphs-mcp http://127.0.0.1:9680/mcp/
```

Then start the server in Glyphs with **Edit → Start MCP Server**.
