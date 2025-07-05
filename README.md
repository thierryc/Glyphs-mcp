# glyphs-mcp
Glyphs app mcp server

> ⚠️ **WORK-IN-PROGRESS — QUICK DRAFT**  
> This README is an early draft for discussion only.  
> All architecture notes, command names, and examples **must be reviewed and verified** before any production use.

---

## TL;DR  
An **MCP server** exposes domain-specific “tools” (JSON-RPC methods) to local AI assistants.  
Two transport modes are common:

| Transport | Alias in client configs | Use cases | Pros | Cons |
|-----------|-------------------------|-----------|------|------|
| **Direct command (stdio)** | `"type": "command"` | CLIs, CI | Zero network latency | One tool per process |
| **Server-Sent Events (SSE over HTTP)** | `"type": "sse"` | IDE plug-ins, multi-tool suites | Persistent stream; easy to secure/proxy | Uni-directional push only |

Most modern IDE agents default to an SSE endpoint like `http://127.0.0.1:<port>/sse`.

---

## 1 What’s an MCP server?  
An MCP server is a lightweight process (Python, Node, Go …) that registers “tools” and streams their JSON results back to the calling LLM. Because the protocol is transport-agnostic, the exact same tool definitions can be exposed via either stdio or SSE.

---

## 2 Reference command sets

### 2.1 Figma Dev Mode MCP Server  
| Tool | Purpose |
|------|---------|
| `get_code` | Return React/Vue/Svelte code for the current selection |
| `get_variable_defs` | List design tokens used in the selection |
| `get_code_connect_map` | Map node-IDs to components in your codebase |
| `get_image` | Rasterize or placeholder-export selected frame |

### 2.2 Playwright MCP Server (`@playwright/mcp`)  
| Tool | Purpose |
|------|---------|
| `browser_navigate` | Load a URL |
| `browser_click` | Click an element |
| `browser_type` | Type keys |
| `browser_press_key` | Send special keys |
| `browser_drag` | Drag-and-drop |
| `browser_take_screenshot` | PNG snapshot |
| `browser_select_option` | Choose from `<select>` |
| `browser_file_upload` | Attach a file |
| `browser_wait_for` | Wait for selector/URL |
| `browser_close` | End session |

---

## 3 GlyphsApp MCP Server – Proposed commands (v2)

| Tool name | Arguments | Description |
|-----------|-----------|-------------|
| `list_open_fonts` | — | List all open fonts and basic metadata. |
| `get_glyph_metrics` | `font_id`, `glyph_name` | Return width, LSB, RSB, anchors. |
| `set_side_bearings` | `font_id`, `glyph_name`, `lsb`, `rsb` | Update bearings and redraw. |
| `export_selection_svg` | `font_id`, `[glyph_names]` | Export glyphs as SVG. |
| `auto_kern_pair` | `font_id`, `left_glyph`, `right_glyph`, `engine="ht" \| "ai"` | Suggest **or** apply kerning with either HT Letterspacer heuristics or an AI model trained on well-kerned fonts. |
| `auto_space_font` | `font_id`, `engine="ht" \| "ai"` | Generate side bearings for the whole font using the selected engine. |
| `generate_variable_font` | `font_id`, `out_path` | Export a Variable Font. |
| `apply_filter` | `font_id`, `filter_name`, `params` | Run a Glyphs filter plug-in. |
| `get_selected_layer_outline` | `font_id` | Return current layer outline data. |
| `rename_glyph` | `font_id`, `old_name`, `new_name` | Batch-rename a glyph. |
| `batch_generate_png` | `font_id`, `[glyph_names]`, `size` | Rasterize glyphs at a given ppem. |

*Both `auto_*` tools return JSON like:*  
`{ "suggested": <number>, "applied": true|false, "engine": "ht"|"ai" }`.

---

## 4 Macro TODO list

1. **Scaffold** – `pip install fastmcp glyphsLib` and stub each tool.  
2. **Transport** – `fastmcp run --transport sse --port 8765 glyphs_server:app`; add `--stdio` wrapper.  
3. **Sessions** – Maintain `{font_id: GSFont}` map; clean unused IDs.  
4. **Security** – Optional bearer-token header.  
5. **DX** – Ship pre-filled `.cursor/mcp.json` snippet.  
6. **Tests** – Unit tests with a small test font; end-to-end via Playwright + AppleScript.  
7. **Docs** – Add `docs/USAGE.md` with sample prompts.  
8. **Roadmap** – Async job queue and optional WebSocket mirror.

---

Links: 

https://standardcomputation.com

https://vimeo.com/1059769678

https://huggingface.co/learn/mcp-course/unit0/introduction



Happy hacking! ✌️
