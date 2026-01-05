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

## Security & Transport Notes
- The server binds locally starting at port 9680; keep it on loopback during development.
- Responses stream via MCP Streamable HTTP (SSE under the hood); preserve any `Mcp-Session-Id` header returned by the server.
- If you open `http://127.0.0.1:9680/mcp/` in a browser, the server returns a JSON discovery payload; MCP clients should connect with `Accept: text/event-stream`.
- Add authentication (for example bearer tokens) before exposing the transport beyond localhost.

## Helper Resources
- Guide: `glyphs://glyphs-mcp/guide`
- Docs index: `glyphs://glyphs-mcp/docs/index.json`

## IDE Configuration
Claude Desktop example:

```
{
  "globalShortcut": "Alt+Ctrl+Cmd+*",
  "mcpServers": {
    "glyphs-mcp-server": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://127.0.0.1:9680/mcp/",
        "--header"
      ]
    }
  }
}
```

Claude Desktop spawns MCP servers without your login shell, so it often falls back to an older embedded Node. Keeping `PATH` pointed at a Node 20+ install ensures `npx` resolves the recent `mcp-remote` CLI.

Prefer Python instead of Node? Install the proxy CLI and reference it directly:

```
pip3 install --user mcp-proxy
```

```
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

The `PATH` override pins Claude Desktop to the `mcp-proxy` shim that `pip3` drops into Python 3.12’s `bin` directory. If your interpreter lives elsewhere (for example a `pyenv` or Homebrew install), replace that prefix with `$(python3 -m site --user-base)/bin`.
