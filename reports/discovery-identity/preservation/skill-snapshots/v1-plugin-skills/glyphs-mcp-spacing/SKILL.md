---
name: glyphs-mcp-spacing
description: Review, compare, and safely apply Glyphs spacing suggestions with class-aware references, normalized negative-bearing guards, tabular-width checks, dry runs, and visual proofing. Use for sidebearings, advance widths, spacing audits, reference-font comparisons, or approved spacing changes.
---

# Glyphs MCP spacing

Use class-aware review, normalized safeguards, and visual proofing. Negative sidebearings are legal; suspect them only when magnitude, class, geometry, or their effect across word spaces is implausible. Read [Negative sidebearings and spacing safeguards](references/negative-sidebearings.md) when a result is negative, blocked, exempted, or manually overridden.

## Safe workflow

1. Connect to `glyphs-mcp-server` and call `list_open_fonts`.
2. Identify the exact font index and master ID before calculating anything.
3. Inspect UPM, x-height, cap height, italic angle, fixed-pitch status, current width and bearings, metrics keys, automatic alignment, whether current metrics are trusted or placeholders, and glyph category/Unicode data.
4. Call `review_spacing` before mutation. Prefer omitted/`"auto"` `referenceGlyph`, then verify every `resolvedReferenceGlyph`, `referenceFallback`, and `glyphClass`.
5. Inspect normalized metrics, negative-bearing warnings/blocks, width assessment, tabular provenance, confidence, and current-metric trust. Do not use a delta from untrusted placeholder metrics as proof that a proposal is wrong.
6. Review representative glyphs before approving a set:
   - Uppercase: `H O J T V W Y`
   - Lowercase: `n o f j`
   - Figures: `one seven` and all default figures
   - Narrow punctuation, quotation marks, and any marks in scope
7. Preserve width only when fixed-pitch metadata, equal default figures, width links, or explicit intent supports it. Do not infer monospacing from a family name or typewriter styling.
8. Call `apply_spacing` with `dry_run=true` using the exact defaults, rules, guards, clamps, and intended overrides. Confirm its guard assessments match review.
9. Require explicit authorization unless the user already clearly requested mutation. Apply only eligible results. Disclose `overrides.blockedGlyphs` and `overrides.manualReviewGlyphs` separately; an override does not make the original assessment safe.
10. Re-read applied metrics and print a verification table. Never save the Glyphs document automatically.

## Comparison workflow

When comparing another font:

- State the exact source font and master.
- State the scaling method. Do not blindly multiply by UPM ratio when cap heights or x-heights differ.
- Prefer cap-height scaling for capitals/figures and x-height scaling for lowercase where appropriate. Report UPM and design-height scaling when they materially disagree.
- Treat reference metrics as evidence, not ground truth.

Print a table with: Glyph, Current LSB/RSB, Calculated LSB/RSB, Reference LSB/RSB, calculated-minus-reference differences, resolved reference, normalized calculated bearings, and warning/block state.

## Proofing

Recommend visual proofs: `HHHOHH`, `HOHOHO`, `AVAYAW`, `JHJOJ`, `nnnon`, `nonono`, `f` beside rounds/verticals/spaces, a complete repeated-figure proof, and narrow punctuation beside capitals, lowercase, figures, and spaces.

Use `set_spacing_params` and `set_spacing_guides` only when requested. For the full tool surface, see the [command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx).
