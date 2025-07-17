# Glyphs MCP
A Machine‑Control‑Protocol server for [Glyphs](https://glyphsapp.com) that exposes font‑specific tools to AI/LLM agents.

> **Status: Work in progress – the API may change at any time.**

---

## What is an MCP server?

A *Machine‑Control‑Protocol* server is a lightweight process that:

1. **Registers tools** (JSON‑RPC methods) written in the host language (Python here).  
2. **Streams JSON output** back to the calling agent. 

---

## Command set (v0.3)

| Tool | Description |
|------|-------------|
| `list_open_fonts` | List all open fonts and basic metadata. |
| `get_font_glyphs` | Return glyph list and key attributes for a font. |
| `get_font_masters` | Detailed master information for a font. |
| `get_font_instances` | List instances and their interpolation data. |
| `get_glyph_details` | Full glyph data including layers, paths, components. |
| `get_font_kerning` | All kerning pairs for a given master. |
| `create_glyph` | Add a new glyph to the font. |
| `delete_glyph` | Remove a glyph from the font. |
| `update_glyph_properties` | Change unicode, category, export flags, etc. |
| `copy_glyph` | Duplicate outlines / components from one glyph to another. |
| `update_glyph_metrics` | Adjust width and side‑bearings. |
| `get_glyph_components` | Inspect components used in a glyph. |
| `add_component_to_glyph` | Append a component to a glyph layer. |
| `add_anchor_to_glyph` | Add an anchor to a glyph layer. |
| `set_kerning_pair` | Set or remove a kerning value. |
| `get_selected_glyphs` | Info about glyphs currently selected in UI. |
| `get_selected_font_and_master` | Current font + master and selection snapshot. |
| `get_glyph_paths` | Export paths in a JSON format suitable for LLM editing. |
| `set_glyph_paths` | Replace glyph paths from JSON. |
| `execute_code` | Execute arbitrary Python in the Glyphs context. |
| `execute_code_with_context` | Execute Python with injected helper objects. |
| `save_font` | Save the active font (optionally to a new path). |

---

## Build the Glyphs plug‑in

```bash
# from the project root
source glyphs-build-env/bin/activate

# pull vendored libs & build the bundle
src/glyphs-mcp/scripts/vendor_deps.sh
```

The script updates the plugin’s `site‑packages` inside `src/glyphs-mcp/Glyphs MCP.glyphsPlugin`.
Copy **or create a symlink (alias)** of this plugin into `~/Library/Application Support/Glyphs 3/Plugins/`, then restart Glyphs.

To start the Glyphs MCP server, open the **Edit** menu and choose **Start MCP Server**.

Open the **Macro Panel** to access the console.

---

## Contributing
PRs are welcome. Run `pytest` and `black .` before submitting.

---
