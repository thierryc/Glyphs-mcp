---
name: glyphs-mcp-italic-first-pass
description: Use this skill for a guarded experimental italic or oblique construction draft from Roman glyphs, including one glyph, a selection, a named scope, or corresponding masters across a family.
---

# Glyphs MCP italic first pass

Use this skill for a guarded Roman-to-italic first pass. Its goal is to help a
designer begin an emphasis companion to the Roman. It accelerates construction;
it does not create, replace, or claim optical completion of a designed italic.

## Core rules

- Use the typed candidate workflow for every italic first pass. Preview and
  session review do not alter the font; materialization and acceptance require
  dry run, exact targets, and explicit approval before confirmation.
- Read current font, master, and selection before mutation.
- Resolve an explicit Roman-to-italic master pair for every requested master.
  Do not interpret "all masters" as one source/target pair.
- Default angle is `12.0` degrees unless the user specifies another value.
- Interpret `angle` as a Glyphs source/Transformations angle: positive values lean Latin outlines to the right. In exported OpenType/UFO metadata, the corresponding `post.italicAngle` / `slnt` value is negative (`+12` in Glyphs source convention maps to about `-12` in exported font convention).
- Before outline work, verify the target italic master's `italicAngle` from `get_font_masters` equals `+angle` within `0.01`; do not use `slantAngle`, which reports the separate `postscriptSlantAngle` custom parameter.
- If the target master `italicAngle` differs, run `set_master_italic_angle` with `dry_run=true`, show the before/after, and only set it with `confirm=true` after explicit approval.
- Candidate acceptance preserves target topology. Before preview, every target
  master layer must therefore be an untouched Roman-compatible bootstrap copy,
  not an empty layer. The candidate may change approved coordinates, anchors,
  component placement, and metrics; it must not create topology.
- Copy components as live components, but do not skew component transforms or component outlines; component shapes should resolve from their own italic master layers.
- Default `compatibility_mode` is `preserve_if_possible`; path compatibility is useful but not required.
- Before `slant_mode="cursivy"`, run `review_master_stem_metrics` for the target italic master.
- Default to `slant_mode="balanced"`. Use Cursivy only when the designer
  explicitly requests the legacy Transformations-backed construction or needs
  comparison with an existing Cursivy workflow. Balanced builds Raw, applies the
  pure-Python conservative correction at partial strength, interpolates using
  `curve_strength`, and then applies the independent final
  `stem_compensation`. It never calls the Glyphs Transformations filter.
- Balanced defaults to `curve_strength=0.75` and
  `stem_compensation=1.0`. Pass `slant_mode="balanced"` explicitly because the
  tool's omitted-argument compatibility default remains Cursivy.
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
- Treat the symbol slant tiers below as Unicode-aware review prompts, never as
  automatic exclusions or transformations. Report affected glyphs and ask the
  designer whether to include, exclude, or defer them.
- If Cursivy stems are missing, ask whether to set stems, measure suggestions, use raw slant, or stop.
- Call `preview_italic_first_pass_candidate` to generate detached proposals.
- Diagnostic preview partitioning is read-only and does not require approval.
  Approval is required only before mutation or before explicitly omitting a
  diagnosed glyph from the final pass.
- Call `review_outline_candidate_session`, then
  `accept_outline_candidate_session` with `dry_run=true` and the exact review
  token before any mutating call.
- Only accept after explicit approval with `confirm=true` and the unexpired,
  fingerprint-bound token.
- Never auto-save the font.
- Materialize only when the user wants to edit the proposed layers manually.
  Re-review exact edits and accept with the newly issued token. Never recreate
  or delete candidate layers through arbitrary code or LLM memory.

## Workflow

1. Read context:
   - `get_selected_font_and_master`
   - `get_font_masters`
   - `get_selected_glyphs` when scope may be selection-based
2. Resolve the master-pair plan:
   - map every Roman source master to one target italic master
   - verify matching non-italic axis coordinates and the intended italic-axis
     coordinate
   - if targets do not exist, show the exact creation/bootstrap plan and wait
     for approval
   - after approval, `execute_code_with_context` may create only the reviewed
     target master shells and untouched copies of their corresponding Roman
     layers; append a master before setting font-dependent properties
   - never draw, slant, recreate candidate layers, or delete layers through
     generic code
   - re-read masters and representative target paths/components; stop if any
     target is empty, mismatched, or not Roman-compatible
3. Resolve scope:
   - `current_glyph`
   - `selected_glyphs`
   - `glyph_names`
   - `all_glyphs`
4. Resolve Unicode values for the scoped glyphs:
   - use Unicode values already returned for selection-based scopes
   - call `get_font_glyphs` when the scope needs a whole-font name-to-Unicode map
   - report any glyphs covered by the symbol slant policy below
   - ask whether to include, explicitly exclude, or defer each affected group
5. Verify every target master italic angle:
   - call `get_font_masters`
   - compare each target's `italicAngle` to `+angle` within `0.01`
   - dry-run every required `set_master_italic_angle` change
   - summarize all before/after values together and wait for one explicit
     approval before confirming the exact batch
6. If using Cursivy, call `review_master_stem_metrics` for all targets:
   - if missing, call `set_master_stem_metrics` only after approval and with `dry_run=true` first
7. Call `preview_italic_first_pass_candidate` once per resolved master pair,
   always passing `slant_mode` explicitly and keeping construction parameters
   identical unless the designer approved pair-specific differences.
8. If a preview blocks without useful glyph details, diagnose with existing
   tools instead of requesting a new public tool:
   - rerun detached previews with deterministic halves of the same
     `glyph_names` scope until each failing glyph is isolated
   - do not add `skip_glyphs` during diagnosis
   - clear disposable successful diagnostic sessions with
     `set_outline_candidate_overlay`
   - for an isolated glyph, compare `get_glyph_paths` and recursively inspect
     `get_glyph_components` in the source and target masters
   - report topology, component chain/matrix, master mismatch, or other known
     evidence; never infer an unreported safety verdict
   - if `topology_change_blocked:<glyph>` persists while source and target path
     topology are identical, classify it as a candidate-adapter serialization
     regression; stop and report it instead of skipping a valid glyph
9. Summarize the returned candidate sessions and diagnosed blockers:
   - glyph count and blocked glyphs
   - missing stems
   - protected glyph warnings
   - symbol slant advisories and the designer's chosen handling
   - compatibility mode and compatibility issues
   - live component preservation, component chain/matrix diagnostics, and any
     blocking reason
   - target glyphs that would be created
10. If the final batch is blocked, ask whether to rebuild, explicitly exclude,
    or defer each diagnosed glyph. Only after that decision, regenerate the
    complete approved scope with the exact `skip_glyphs` list.
11. Ask the designer to inspect **View > Show Glyphs MCP Candidate**. If manual
    editing is requested, dry-run and confirm
    `materialize_outline_candidate_session`, then wait for those edits.
12. Call `review_outline_candidate_session` for every final session. Stop on
    stale source, topology, component, off-grid, or operation-external changes.
13. Call `accept_outline_candidate_session` with `dry_run=true` and each exact
    review token. Summarize the complete master/session change set and ask for
    approval.
14. After approval, confirm the reviewed sessions sequentially with their same
    valid tokens. This is not an atomic multi-master transaction; on any
    failure, stop immediately and report which sessions were already accepted.
15. Re-read every target master, verify candidate cleanup and backup
    preservation, and list glyphs that still need manual optical work.

## Defaults

Use these defaults unless the user says otherwise:

```json
{
  "scope": "selected_glyphs",
  "angle": 12.0,
  "slant_mode": "balanced",
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
  "origin": 3
}
```

## Symbol slant policy

Use these tiers to prompt review before a mechanical slant. Match glyphs by
Unicode value, not by Glyphs glyph name. Unicode identity is evidence for
review, not a design verdict.

- **Empirical upright candidates:** `U+00A4 ¤`, `U+00A9 ©`, `U+00AE ®`,
  `U+00B0 °`, and `U+212E ℮`. The smaller-coverage sample also supports
  `U+2190 ←`, `U+2191 ↑`, `U+2192 →`, `U+2193 ↓`, and `U+25A0 ■`.
- **Traditionally upright mathematical operators:** `U+002B +`,
  `U+003C–U+003E <=>`, `U+00AC ¬`, `U+00B1 ±`, `U+00D7 ×`, `U+00F7 ÷`,
  `U+220F ∏`, `U+2211 ∑`, `U+2212 −`, `U+221A √`, `U+221E ∞`, `U+222B ∫`,
  `U+2248 ≈`, `U+2260 ≠`, and `U+2264–U+2265 ≤≥`. Traditional math
  typography favors upright operators, but most popular Google text-font
  italics in the reviewed sample slant them.
- **Design-dependent forms:** `U+0023 #`, `U+002A *`, `U+0040 @`, `U+007C |`,
  `U+007E ~`, `U+2022 •`, and `U+2122 ™`. Inspect these visually. For `@`,
  review the enclosure and the internal letter separately.

For every matched glyph, show the tier and ask whether to:

1. include it in the reviewed mechanical slant;
2. exclude it explicitly from that pass; or
3. defer it for manual drawing.

Do not silently add listed glyphs to `skip_glyphs`, change
`protected_glyphs`, preserve Roman outlines, or apply a zero-angle workaround.
The italic master keeps its real `italicAngle`; any upright construction is a
separate, designer-approved drawing decision.

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
- [Google Fonts family metadata](https://fonts.google.com/metadata/fonts)
- [Google Fonts static-font guidance](https://googlefonts.github.io/gf-guide/statics.html)
- [Unicode support for mathematics](https://www.unicode.org/reports/tr25/)
- [Microsoft Latin-1 math character design](https://learn.microsoft.com/en-us/typography/develop/character-design-standards/math)
- [Microsoft OpenType MATH specification](https://learn.microsoft.com/en-us/typography/opentype/spec/math)
- [fontTools StatisticsPen](https://fonttools.readthedocs.io/en/latest/pens/statisticsPen.html)
