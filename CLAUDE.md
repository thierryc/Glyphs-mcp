# CLAUDE.md

This guide briefs Claude Code on how to work with the Glyphs MCP repository.

## Project Overview
- Glyphs MCP is a Model Context Protocol (MCP) server bundled as a Glyphs 3 plugin.
- It exposes GlyphsApp APIs as JSON-RPC tools over the MCP Streamable HTTP transport.
- Python sources live in `src/glyphs-mcp/`; dependencies are vendored into the plugin
  bundle (`Contents/Resources/vendor/`) for zero-config installation.

## Capabilities Exposed to Agents
The shipped tool set focuses on glyph inspection, editing, and project metadata:
- `list_open_fonts`, `get_font_masters`, `get_font_instances` for font-level information.
- `get_glyph_details`, `get_glyph_paths`, `get_glyph_components`, `get_selected_glyphs` for glyph structure.
- `create_glyph`, `delete_glyph`, `copy_glyph`, `add_component_to_glyph`, `add_anchor_to_glyph` for building glyphs.
- `update_glyph_metrics`, `update_glyph_properties`, `set_kerning_pair`, `save_font` for metrics and persistence.
- `execute_code`, `execute_code_with_context`, `get_selected_font_and_master` for scripted automation inside Glyphs.

Refer to `README.md` for the complete table of supported tools and descriptions.

## Repository Layout Highlights
- `src/glyphs-mcp/` — MCP implementation, plugin bundle, and helper scripts.
- `Documentations/` — Generated ObjectWrapper docs that get copied into the plugin.
- `glyphs-build-env/` — Optional local virtual environment for development tooling.
- `README.md` — High-level overview, tool catalog, and IDE configuration snippets.

## Build & Run Workflow

### Quick Start
1. Run `python3 install.py` to vendor dependencies and install the plugin
2. Restart Glyphs, then choose **Edit → Start MCP Server**. The server listens on `http://127.0.0.1:9680/mcp/` using Streamable HTTP.

### Building Vendored Releases
```bash
# Update pinned requirements (target 3.11 for broadest compatibility)
uv pip compile pyproject.toml --python-version 3.11 --upgrade -o requirements.txt

# Download and bundle dependencies (uses Python version from your interpreter)
python3.11 src/glyphs-mcp/scripts/vendor_deps.py   # for 3.11 bundle
python3.14 src/glyphs-mcp/scripts/vendor_deps.py   # for 3.14 bundle

# Plugin is now ~73MB with all deps included
```

After regenerating ObjectWrapper documentation, update the bundled copy with:

```
python src/glyphs-mcp/scripts/copy_documentation.py
```

## Security & Transport Notes
- The server binds locally starting at port 9680; keep it on loopback during development.
- Responses stream via MCP Streamable HTTP (SSE under the hood); preserve any `Mcp-Session-Id` header returned by the server.
- Add authentication (for example bearer tokens) before exposing the transport beyond localhost.

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
