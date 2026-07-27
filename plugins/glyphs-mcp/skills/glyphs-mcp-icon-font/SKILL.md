---
name: glyphs-mcp-icon-font
description: Use this skill when the task is to audit or maintain Unicode or PUA assignments specifically in an icon or symbol font, allocate stable values for new icons, compare a previous icon mapping, or apply reviewed icon-font encoding changes safely in Glyphs.
---

# Glyphs MCP icon font

Use this skill for stable icon-font encoding, not icon drawing or general PUA work.

## Core rules

- Use only `review_unicode_assignments` and `apply_unicode_assignments` for assignment batches.
- Run review without allocation before proposing any value.
- Preserve every existing assignment.
- For a released font, require its previous map before allocation. Without one, audit only unless the user explicitly authorizes a new baseline.
- Never infer standard Unicode from an icon name or drawing.
- Target selected or named glyphs by default. Use whole-font scope only when explicitly requested.
- Default private icon allocation to BMP PUA; accept an explicit caller-supplied range.
- Require a dry run and explicit approval before applying with `confirm=true`.
- Never save the font.
- Do not create manifests, canonical IDs, CSS, TypeScript, accessibility metadata, Figma workflows, or exported-font `cmap` reports.

## Workflow

1. Call `list_open_fonts`, then inspect the target with `get_font_glyphs`.
2. Establish whether the font is unreleased or already released. Obtain the previous map for a released font.
3. Call `review_unicode_assignments` with `allocate_unencoded=false`.
4. Summarize collisions, invalid values, export-state warnings, multiple assignments, previous-map changes, and range capacity.
5. If allocation is requested and allowed, review again with `allocate_unencoded=true`, the selected or named glyphs, the previous map, and any reserved values or custom range.
6. Present the exact proposals and private-agreement warning. Do not reinterpret their meaning.
7. Pass the reviewed assignments to `apply_unicode_assignments` with `dry_run=true`.
8. After explicit approval, repeat with `confirm=true`, review the affected glyphs again, and report verification without saving.

For drawing or outline work, use `glyphs-mcp-outlines-docs`. For metrics, use `glyphs-mcp-spacing`.

## Deeper references

- [Unicode assignment tools](https://github.com/thierryc/Glyphs-mcp/blob/main/content/contributor/unicode-assignment-tools.md)
- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
- [Project briefing](https://github.com/thierryc/Glyphs-mcp/blob/main/CODEX.md)
