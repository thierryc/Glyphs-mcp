---
name: glyphs-mcp-spacing
description: Use this skill when the task is to review spacing, inspect sidebearing or width suggestions, or apply approved spacing changes with a dry run first.
---

# Glyphs MCP spacing

Use this skill for guarded spacing review and apply workflows.

## Core rules

- Prefer the `Spacing` tool profile when spacing is the only focus.
- Inspect current font, master, and selection before mutation.
- Run `review_spacing` before any apply step.
- Always run `apply_spacing` with `dry_run=true` before a mutating call.
- Mention `set_spacing_params` and `set_spacing_guides` only as optional supporting tools.
- Never auto-save the font.

## Workflow

1. Read the current context first:
   - `get_selected_font_and_master`
   - `get_selected_glyphs`
   - `get_glyph_details` only if the review needs more shape or metrics context
2. Run `review_spacing` and summarize:
   - reviewed glyphs
   - proposed sidebearing or width changes
   - assumptions or outliers
3. If the user wants to proceed, run `apply_spacing` with `dry_run=true`.
4. Report the proposed changes in plain language before any mutation.
5. Only after explicit approval, run the real apply call.
6. Re-read the affected state or summarize returned changes, and call out any glyphs that still need manual review.

## Optional helpers

- `set_spacing_params` for font or master-level spacing parameters
- `set_spacing_guides` for visual measurement guides

Use them only when the user explicitly wants those supporting adjustments.

## Deeper references

- [Command set](../../content/reference/command-set.mdx)
- [Project briefing](../../CODEX.md)
- [Tool profiles](../../src/glyphs-mcp/Glyphs%20MCP.glyphsPlugin/Contents/Resources/tool_profiles.py)
