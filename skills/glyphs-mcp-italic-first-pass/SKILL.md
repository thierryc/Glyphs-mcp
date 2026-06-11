---
name: glyphs-mcp-italic-first-pass
description: Use this skill when the task is to create a first-pass italic or oblique set from roman glyphs, selected glyphs, or one current glyph by copying layers and applying a guarded slant.
---

# Glyphs MCP italic first pass

Use this skill for a guarded roman-to-italic first pass. It accelerates the work; it does not claim optical completion.

## Core rules

- Prefer the `Paths / Outlines` profile for review-only work, or `Editing` when applying.
- Read current font, master, and selection before mutation.
- Default angle is `9.4` degrees unless the user specifies another value.
- Default `compatibility_mode` is `preserve_if_possible`; path compatibility is useful but not required.
- Before `slant_mode="cursivy"`, run `review_master_stem_metrics` for the target italic master.
- If Cursivy stems are missing, ask whether to set stems, measure suggestions, use raw slant, or stop.
- Run `review_italic_first_pass` before `apply_italic_first_pass`.
- Always run `apply_italic_first_pass` with `dry_run=true` before any mutating call.
- Only mutate after explicit approval with `confirm=true`.
- Never auto-save the font.

## Workflow

1. Read context:
   - `get_selected_font_and_master`
   - `get_font_masters`
   - `get_selected_glyphs` when scope may be selection-based
2. Resolve scope:
   - `current_glyph`
   - `selected_glyphs`
   - `glyph_names`
   - `all_glyphs`
3. Resolve source roman and target italic masters.
4. If using Cursivy:
   - call `review_master_stem_metrics`
   - if missing, call `set_master_stem_metrics` only after approval and with `dry_run=true` first
5. Call `review_italic_first_pass`.
6. Summarize:
   - glyph count and blocked glyphs
   - missing stems
   - protected glyph warnings
   - compatibility mode and compatibility issues
   - target glyphs that would be created
7. If the user approves, call `apply_italic_first_pass` with `dry_run=true`.
8. After approval of the dry run, call `apply_italic_first_pass` with `confirm=true`.
9. Re-read or summarize returned results and list glyphs that still need manual optical work.

## Defaults

Use these defaults unless the user says otherwise:

```json
{
  "scope": "selected_glyphs",
  "angle": 9.4,
  "slant_mode": "cursivy",
  "stem_policy": "require_existing",
  "compatibility_mode": "preserve_if_possible",
  "copy_options": {
    "paths": true,
    "components": true,
    "anchors": true,
    "metrics": true
  },
  "origin": 3,
  "backup": true
}
```

## Manual review reminders

Warn that mechanically slanted glyphs need review, especially `a`, `e`, `f`, `g`, `k`, `v`, `w`, `x`, `y`, punctuation, brackets, braces, quotes, and symbols.

Kerning replacement is not part of this v1 skill. If the user wants kerning copied from roman to italic, treat it as a separate follow-up workflow.

## Deeper references

- [Command set](../../content/reference/command-set.mdx)
- [Glyphs Transformations docs](../../Documentations/Markdown/086_filters_filters_built-in_transformations.md)
- [Stem metrics docs](../../Documentations/Markdown/041_font-info_masters.md)
