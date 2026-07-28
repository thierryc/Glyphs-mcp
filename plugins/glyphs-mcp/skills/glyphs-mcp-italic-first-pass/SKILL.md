---
name: glyphs-mcp-italic-first-pass
description: Use this skill for an experimental first-pass italic or oblique construction draft from Roman glyphs, selected glyphs, or one current glyph.
---

# Glyphs MCP italic first pass

Use this skill for a guarded Roman-to-italic first pass. Its goal is to help a
designer begin an emphasis companion to the Roman. It accelerates construction;
it does not create, replace, or claim optical completion of a designed italic.

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
- Prefer `slant_mode="balanced"` when the user wants the recommended
  experimental reproducible option. Balanced builds Raw, applies the
  pure-Python conservative correction at partial strength, interpolates using
  `curve_strength`, and then applies the independent final
  `stem_compensation`. It never calls the Glyphs Transformations filter.
- Balanced defaults to `curve_strength=0.75` and
  `stem_compensation=1.0`. Full final compensation can neutralize visible
  intermediate differences on accepted stems. Keep omitted `slant_mode` calls
  defaulting to Cursivy for compatibility.
- The Inter/Noto Sans/IBM Plex Sans validation preserved topology and source
  layers, accepted 135/102/102 stem pairs, and passed because every
  non-commuting component construction was blocked before application.
- For reflected, rotated, or non-uniformly scaled component constructions,
  cycles, unreadable transforms, or component-master mismatches, stop after
  review and ask the designer to inspect or rebuild the construction. Do not
  silently omit it or claim that the generated direction is safe.
- Do not exclude glyphs by name or Unicode category. Use the reported outline
  and recursive component analysis. If the user explicitly approves a smaller
  safe scope, rerun with `skip_glyphs`.
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
   - live component preservation, component chain/matrix diagnostics, and any
     blocking reason
   - target glyphs that would be created
8. If review blocks the batch, pause. Only after the designer explicitly
   chooses a smaller scope, rerun review with `skip_glyphs`.
9. If the user approves, call `apply_italic_first_pass` with `dry_run=true`.
10. After approval of the dry run, call `apply_italic_first_pass` with `confirm=true`.
11. Re-read or summarize returned results and list glyphs that still need manual optical work.

## Defaults

Use these defaults unless the user says otherwise:

```json
{
  "scope": "selected_glyphs",
  "angle": 12.0,
  "slant_mode": "cursivy",
  "curve_strength": 0.75,
  "stem_compensation": 1.0,
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

Balanced mode additionally shears copied anchors around the selected origin.
It recursively checks whether each component transform commutes with the
requested shear within `1e-6`. Translation and commuting linear transforms
such as uniform scale are permitted. Reflection, rotation, non-uniform scale,
cycles, unreadable transforms, and an explicit component master that does not
resolve to the target master block that glyph. Raw and Cursivy retain their
legacy component and anchor behavior.

## Manual review reminders

Warn that the output is a construction draft, not the italic design. The
designer still owns optical form, rhythm, spacing, kerning, alternates,
interpolation, and proofing. Mechanically transformed glyphs need review,
especially `a`, `e`, `f`, `g`, `k`, `v`, `w`, `x`, `y`, punctuation,
brackets, braces, quotes, and symbols.

Kerning replacement is not part of this v1 skill. If the user wants kerning copied from roman to italic, treat it as a separate follow-up workflow.

## Deeper references

- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
- [Broad-Latin benchmark](https://github.com/thierryc/Glyphs-mcp/blob/main/content/contributor/italic-balanced-broad-latin-benchmark.md)
- [Glyphs Transformations docs](https://github.com/thierryc/Glyphs-mcp/blob/main/Documentations/Markdown/086_filters_filters_built-in_transformations.md)
- [Stem metrics docs](https://github.com/thierryc/Glyphs-mcp/blob/main/Documentations/Markdown/041_font-info_masters.md)
