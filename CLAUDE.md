# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Model Context Protocol (MCP) server designed to expose GlyphsApp functionality as tools to AI assistants. The server provides domain-specific typography and font manipulation capabilities through JSON-RPC methods.

## Planned Architecture

### Transport Modes
- **Direct command (stdio)**: For CLIs and CI environments
- **Streamable HTTP**: For IDE plugins and multi-tool suites with optional SSE streaming

### Core Dependencies
- `fastmcp` - MCP server framework
- `glyphsLib` - Python library for Glyphs font manipulation
- PyTorch - For AI-powered kerning and spacing features

### Running the Server

The MCP server runs as a Glyphs App plugin, not as a standalone command:

1. **Install the plugin**: Copy or symlink the plugin bundle to `~/Library/Application Support/Glyphs 3/Plugins/`
2. **Restart Glyphs App**
3. **Start the server**: Go to **Edit** menu → **Start Glyphs MCP Server**
4. **Server available at**: `http://127.0.0.1:9680/` (Streamable HTTP with SSE support)

The server runs in a background daemon thread within Glyphs App and automatically finds an available port starting from 9680.

### Security Considerations for Streamable HTTP

When using Streamable HTTP transport, implement these security measures:

- **Origin validation**: Validate `Origin` header to prevent DNS rebinding attacks
- **Local binding**: Bind to localhost when possible to limit exposure
- **Authentication**: Implement bearer token authentication for production use
- **Session management**: Use `Mcp-Session-Id` header for session tracking
- **Connection security**: Support TLS in production environments

## Planned MCP Tools

The server will expose these font manipulation tools:

- `list_open_fonts` - List all open fonts and metadata
- `get_glyph_metrics` - Return width, LSB, RSB, anchors for a glyph
- `set_side_bearings` - Update glyph bearings
- `export_selection_svg` - Export glyphs as SVG
- `auto_kern_pair` - AI/HT-powered kerning suggestions
- `auto_space_font` - Generate side bearings for entire font
- `generate_variable_font` - Export Variable Font
- `apply_filter` - Run Glyphs filter plugins
- `get_selected_layer_outline` - Return current layer outline data
- `rename_glyph` - Batch rename glyphs
- `batch_generate_png` - Rasterize glyphs

## Development Phases

1. **Scaffold** - Create basic MCP server structure
2. **Transport** - Implement Streamable HTTP and stdio transports
3. **Sessions** - Font session management with cleanup
4. **Security** - Optional bearer token authentication
5. **DX** - IDE configuration snippets
6. **Tests** - Unit tests with test fonts and E2E with Playwright
7. **Documentation** - Usage examples and sample prompts
8. **Roadmap** - Async job queue and WebSocket support

## Testing Strategy

- Unit tests using small test fonts
- End-to-end testing via Playwright + AppleScript for GlyphsApp integration
- ML model validation for AI-powered kerning features

## Project Status

This repository has a working MCP server implementation with:
- MCP Streamable HTTP transport at `http://127.0.0.1:9680/`
- Origin header validation for security
- Session management with `Mcp-Session-Id` header
- Proper SSE streaming support
- 40+ font manipulation tools

## IDE Configuration

For Continue plugin, use:
```yaml
mcpServers:
  - name: Glyphs MCP
    type: sse
    url: http://127.0.0.1:9680/
```