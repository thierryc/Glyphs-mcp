# Troubleshoot a shape switch

## Incompatible layers

Group by glyph, master association and design-coordinate rule. Match each
corresponding master to its layer in the region. Compare paths and components
in native shape order and verify contour direction, start and segment types.
For combined Intermediate and Alternate layers, check their positions and
correspondence within the active interpolation set. For reverse brackets,
confirm that the bounded master layer and blank-rule partner supply the
intended drawings. Review interpolation before attempting any outline repair.

## Coordinates and boundaries

Compare internal master and instance values, the effective Axis Location and
Axis Mappings, the variable export's origin and range, and the binary's
`fvar` and `avar`. An exported user coordinate is normalized from the
`fvar` min/default/max and then mapped by `avar` when present. GSUB
Feature Variations compare normalized coordinates. Keep both design and
exported user coordinates in the proof and identify axes by tag in the binary.
If the conversion is ambiguous or the requested threshold lies outside the
export, resolve it before changing source.

Read the compiled bounds and test equality using a shaper. The Handbook
documents inclusive lower bounds for `condition` despite its `<` notation.
The Glyphs 4 native Alternate-layer matcher documents inclusive bounds.
Prove the effective lower and upper behavior in the binary, especially for
adjacent or overlapping regions. At each boundary, use the closest practical
values that stay distinct after normalization, mapping and quantization. Report
when the requested exact boundary and the emitted threshold differ, or when a
side is outside the exported range. [Conditional Feature Code](https://handbook.glyphsapp.com/layout/conditional-feature-code/)

## Lookup order

Read the effective tag, script and language system, and the compiled lookup
order. Confirm that the condition selects the expected Feature Variations
record where regions overlap. Trace the glyph sequence into and out of the
contextual lookup. Earlier ligature or alternate lookups can change its input,
and later substitutions can change its output. Check overlaps with automatic
Alternate-layer lookups and use matching and nonmatching text with the same
language, direction and feature settings. [OpenType layout common table formats](https://learn.microsoft.com/en-us/typography/opentype/spec/chapter2#featurevariations-table)

## Static and variable differences

In static exports, inspect the outline selected through the cmap or shaping.
The base glyph's name or ID can stay the same with a different drawing. Check
the exact instance options, the resulting glyph set and class, lookup and
component references before removing the leftover alternate slot. In variable
exports, confirm both drawings are available and shape with the intended
variation coordinates. Preview and source compilation cannot establish these
binary results. Check that both exports were built from the recorded source
revision before diagnosing discrepancies.

## Glyphs 4 native details

The installed Glyphs 4.2 build 4203 Python wrapper documents
`GSLayer.attributes["axisRules"]` as a dictionary keyed by native
`GSAxis.axisId`, with `min` and/or `max` entries in design coordinates.
`GSLayer.attributes["coordinates"]` uses the axis ID for Intermediate
positions. A disposable test on that build confirmed the rule dictionary,
simultaneous `isBraceLayer` and `isBracketLayer` flags, and a bounded master
paired with an Alternate layer carrying an empty rule dictionary. These flags
round-tripped in a format-4 source copy. Verify the source's own format and
round-trip when necessary. The v4 file format serializes rules in axis order,
which differs from the live dictionary. Consult the
[Glyphs 4 documentation workflow](../../glyphs-mcp-development/references/development-docs.md)
for the wrapper and schema. Resolve native IDs from the bound font and
retain unrelated attributes when editing.

A one-axis fixture exported with the same build confirmed automatic `rlig`
switching, a contextual conditional substitution, and static export swaps and
removal via the documented parameters. Reverify the actual font's mappings,
interpolation and features. Use the Handbook for UI concepts and check any
menu path in the installed Glyphs 4 build before relying on it.
