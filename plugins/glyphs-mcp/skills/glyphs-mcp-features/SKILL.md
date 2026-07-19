---
name: glyphs-mcp-features
description: Use this skill when the task is to inspect OpenType features, stylistic sets, style sets, character variants, or ssXX glyph groups in Glyphs.
---

# Glyphs MCP features

Use this skill for OpenType feature inspection, especially stylistic-set listings.

## Core rules

- For "style set", "stylistic set", or `ssXX` listing questions, call `list_style_sets` first.
- Use each style set's `showMarkdown` group link in the final answer when available. It should be an HTTP bridge link so clients render it as clickable.
- Do not render linked glyph names as inline code.
- Default to one group-level link per style set; only add per-glyph links if the user asks.
- If `showUrlUnavailableReason` is present, report why links are unavailable.
- Never mutate or auto-save the font for feature inspection.

## Workflow

1. Read current font context with `list_open_fonts`.
2. Call `list_style_sets` for the target font.
3. Summarize each set with:
   - tag and name
   - substitution count
   - group-level `showMarkdown`
   - source glyphs affected by the feature
4. Mention skipped unsupported/contextual rules only when the tool reports warnings.

## Deeper references

- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
- [Project briefing](https://github.com/thierryc/Glyphs-mcp/blob/main/CODEX.md)
- [Tool profiles](https://github.com/thierryc/Glyphs-mcp/blob/main/src/glyphs-mcp/Glyphs%20MCP.glyphsPlugin/Contents/Resources/tool_profiles.py)
