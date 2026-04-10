---
name: glyphs-mcp-kerning
description: Use this skill when the task is to review kerning collisions or near-misses, run the kerning bumper workflow, or apply approved kerning exception changes with a dry run first.
---

# Glyphs MCP kerning

Use this skill for guarded kerning bumper workflows.

## Core rules

- Prefer the `Kerning` tool profile when the task is only about kerning.
- Read current state before mutation.
- Run `review_kerning_bumper` before any apply step.
- Always run `apply_kerning_bumper` with `dry_run=true` before a mutating call.
- Only mutate after explicit user approval and with `confirm=true`.
- Never auto-save the font.

## Workflow

1. Read current state with the smallest useful set of tools:
   - `get_selected_font_and_master`
   - `get_selected_glyphs`
   - `get_font_kerning` or `get_glyph_details` only if the review needs extra context
2. Run `review_kerning_bumper` and summarize:
   - affected glyphs or pairs
   - collision or near-miss findings
   - proposed adjustments
3. If the user wants to proceed, run `apply_kerning_bumper` with `dry_run=true`.
4. Report what would change, including changed and skipped counts if available.
5. Only after explicit approval, run the real apply call with `confirm=true`.
6. Re-read or summarize the affected state and clearly separate:
   - what changed
   - what was skipped
   - anything still needing manual review

## Deeper references

- [Command set](../../content/reference/command-set.mdx)
- [Project briefing](../../CODEX.md)
- [Tool profiles](../../src/glyphs-mcp/Glyphs%20MCP.glyphsPlugin/Contents/Resources/tool_profiles.py)
