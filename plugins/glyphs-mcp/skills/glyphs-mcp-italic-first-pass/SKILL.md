---
name: glyphs-mcp-italic-first-pass
description: Use this skill when the task is to create a first-pass italic or oblique set from roman glyphs, selected glyphs, or one current glyph by copying layers and applying a guarded slant.
---

# Glyphs MCP italic first pass

Use this skill for a guarded roman-to-italic first pass. It accelerates the work; it does not claim optical completion.

## Core rules

- Prefer the `Paths / Outlines` profile for review-only work, or `Editing` when applying.
- Read current font, master, and selection before mutation.
- Default angle is `12.0` degrees unless the user specifies another value.
- Interpret `angle` as a Glyphs source/Transformations angle: positive values lean Latin outlines to the right. In exported OpenType/UFO metadata, the corresponding `post.italicAngle` / `slnt` value is negative (`+12` in Glyphs source convention maps to about `-12` in exported font convention).
- Before outline work, verify the target italic master's `italicAngle` from `get_font_masters` equals `+angle` within `0.01`; do not use `slantAngle`, which reports the separate `postscriptSlantAngle` custom parameter.
- If the target master `italicAngle` differs, run `set_master_italic_angle` with `dry_run=true`, show the before/after, and only set it with `confirm=true` after explicit approval.
- Copy roman paths into the italic master and skew only those copied paths.
- Copy components as live components, but do not skew component transforms or component outlines; component shapes should resolve from their own italic master layers.
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
4. Verify target master italic angle:
   - call `get_font_masters`
   - find the target master by `target_master_id`
   - compare its `italicAngle` to `+angle` within `0.01`
   - if different, call `set_master_italic_angle` with `dry_run=true`
   - summarize the before/after and wait for approval before calling `set_master_italic_angle` with `confirm=true`
5. If using Cursivy:
   - call `review_master_stem_metrics`
   - if missing, call `set_master_stem_metrics` only after approval and with `dry_run=true` first
6. Call `review_italic_first_pass`.
7. Summarize:
   - glyph count and blocked glyphs
   - missing stems
   - protected glyph warnings
   - compatibility mode and compatibility issues
   - live component preservation and any component warnings
   - target glyphs that would be created
8. If the user approves, call `apply_italic_first_pass` with `dry_run=true`.
9. After approval of the dry run, call `apply_italic_first_pass` with `confirm=true`.
10. Re-read or summarize returned results and list glyphs that still need manual optical work.

## Defaults

Use these defaults unless the user says otherwise:

```json
{
  "scope": "selected_glyphs",
  "angle": 12.0,
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

## Component Position Handling

When `copy_options.components=true`, preserve components as live components. Do not decompose them and do not skew their outlines, scale, rotation, or internal transform, because component glyphs are expected to have their own italic master drawings.

However, component placement must follow the same slant geometry as paths. After copying a component, adjust only its x translation according to its y translation:

`new_x = old_x + tan(angle) * old_y`

Use the Glyphs source angle convention from this skill. If `old_y == 0`, leave the x position unchanged.

This keeps baseline components unmoved while shifting components placed above or below the baseline so they align with the slanted path geometry.

## Manual review reminders

Warn that mechanically slanted glyphs need review, especially `a`, `e`, `f`, `g`, `k`, `v`, `w`, `x`, `y`, punctuation, brackets, braces, quotes, and symbols.

Kerning replacement is not part of this v1 skill. If the user wants kerning copied from roman to italic, treat it as a separate follow-up workflow.

## Deeper references

- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
- [Glyphs Transformations docs](https://github.com/thierryc/Glyphs-mcp/blob/main/Documentations/Markdown/086_filters_filters_built-in_transformations.md)
- [Stem metrics docs](https://github.com/thierryc/Glyphs-mcp/blob/main/Documentations/Markdown/041_font-info_masters.md)
