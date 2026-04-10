---
name: glyphs-mcp-outlines-docs
description: Use this skill when the task is to inspect or edit outlines, components, anchors, or selected nodes in Glyphs while also using the bundled docs lookup tools to stay grounded.
---

# Glyphs MCP outlines and docs

Use this skill for path editing, component or anchor work, selected-node workflows, and bundled Glyphs docs lookup.

## Core rules

- Prefer dedicated tools first.
- Use `execute_code_with_context` only for multi-step glyph-scoped work that is awkward with the dedicated tools.
- Keep any fallback script minimal, validate targets first, and bound output if needed.
- Use `docs_search` and `docs_get` instead of broad docs loading.
- Re-read affected glyph state after mutation.
- Never auto-save the font.

## Workflow

1. Read the current state first with the smallest useful set:
   - `get_selected_font_and_master`
   - `get_selected_nodes`
   - `get_glyph_paths`
   - `get_glyph_components`
   - `get_glyph_details`
2. Prefer dedicated tools for the actual change:
   - `set_glyph_paths`
   - `add_component_to_glyph`
   - `add_anchor_to_glyph`
   - `review_collinear_handles`
   - `apply_collinear_handles_smooth`
   - compensated-tuning tools only when that workflow is explicitly requested
3. Only use `execute_code_with_context` when the edit spans several glyph-scoped steps and the dedicated tools would be less reliable or less clear.
4. When docs are needed, search first with `docs_search`, then fetch only the relevant page with `docs_get`.
5. After every mutation, re-read the affected glyph or layer state and report what changed.

## Deeper references

- [Command set](../../content/reference/command-set.mdx)
- [Project briefing](../../CODEX.md)
- [Tool profiles](../../src/glyphs-mcp/Glyphs%20MCP.glyphsPlugin/Contents/Resources/tool_profiles.py)
