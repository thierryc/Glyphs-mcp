# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Model Context Protocol (MCP) server designed to expose GlyphsApp functionality as tools to AI assistants. The server provides domain-specific typography and font manipulation capabilities through JSON-RPC methods.

## Planned Architecture

### Transport Modes
- **Direct command (stdio)**: For CLIs and CI environments
- **Server-Sent Events (SSE over HTTP)**: For IDE plugins and multi-tool suites

### Core Dependencies
- `fastmcp` - MCP server framework
- `glyphsLib` - Python library for Glyphs font manipulation
- PyTorch - For AI-powered kerning and spacing features

### Development Commands

Since this is a work-in-progress project, the following commands are planned:

```bash
# Install dependencies
pip install fastmcp glyphsLib

# Run server with SSE transport
fastmcp run --transport sse --port 8765 glyphs_server:app

# Run server with stdio transport
fastmcp run --transport stdio glyphs_server:app
```

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
2. **Transport** - Implement SSE and stdio transports
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

This repository is currently in the planning phase. The README.md contains the complete specification and roadmap. Implementation has not yet begun.