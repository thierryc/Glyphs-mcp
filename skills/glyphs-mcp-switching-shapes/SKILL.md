---
name: glyphs-mcp-switching-shapes
description: Configure and verify glyph shape switches in Glyphs 4 with Glyphs MCP. Use for Alternate (bracket) layers, export-specific glyph replacement, and axis-conditional or contextual OpenType substitutions for a shape switch.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs Switching Shapes

## Inspect the font and resolve the switch

Reuse the verified [Glyphs MCP connection](../glyphs/SKILL.md) and the intended
`document_id`. Follow [document targeting](../glyphs/references/document-targeting.md)
if the binding is missing or the target changed. Inspect the target font
before editing, including unsaved work. Bind the exact glyphs, source drawings,
owning layer IDs, associated master IDs and foreground or background surfaces.

- Use [master reads](../glyphs/references/master-reads.md),
  [layer discovery](../glyphs/references/layer-discovery.md) and
  [instance discovery](../glyphs/references/font-export.md#select-an-exact-instance).
  Record axis names, tags, IDs, design ranges and the exported ranges for the
  requested variable settings. Inspect master positions, static instance
  locations, variable settings, export flags, origin and any designspace
  restrictions. Read the target glyphs' master, Intermediate and Alternate
  layers, including layers with more than one role.
- Inspect the actual layer rules, Intermediate positions, Axis Location and
  Axis Mappings, and relevant font and instance custom parameters. Inventory
  overlapping switches, feature source and dependencies as needed. MCP's
  layer flags and master coordinates cover inventory, while raw layer rules,
  full mapping data and these custom parameters need focused native inspection
  where they are outside the negotiated read surface. Use verified Glyphs 4
  Font Info or a narrowly scoped read-only native inspection of the exact font.
  Keep inspection save-free.
- If any needed switch value is missing or ambiguous, first show the relevant
  axis names, tags and ranges in both coordinate systems where available.
  Ask for the threshold or lower and upper bounds on each relevant axis,
  which shape should appear below, at and above each boundary, and whether
  the values are Glyphs design coordinates or exported variable-font
  coordinates. Clarify how axes combine or which rule wins in any overlap.
  Ask for the desired alternate drawing, matching and nonmatching text
  context, and target static instances or variable settings and formats
  wherever these are unresolved. Wait for the decisions needed to configure
  the switch. Keep all values specific to the current font and request.
- Express layer rules and feature conditions in **design coordinates**.
  Convert requested exported positions through the target export's verified
  mapping and confirm that the resulting regions express the intended switch.
  Preserve family-wide axis mappings unless changing them is in scope.
  See [coordinate and boundary troubleshooting](references/troubleshooting.md#coordinates-and-boundaries).

## Choose the mechanism

### Alternate layers for an axis-driven drawing change

Use Alternate layers, also called bracket layers, for a switch within one
glyph across the designspace, for static and variable export. Create or reuse
an Alternate layer associated with each corresponding master. Apply the same
design-coordinate conditions to the layers in each alternate set. Specify only
the requested limits and leave a bound open when the region extends to the axis
endpoint. Keep the ordinary layers compatible within their set and the
alternate layers compatible within theirs. The two sets can have different
topologies. Check contour order, starts, directions, node types and component
correspondence with the [master compatibility skill](../glyphs-mcp-master-compatibility/SKILL.md).

Use reverse bracket layers when the alternate drawing should also be what the
designer sees on a master in Glyphs. Put that drawing and its bounds on the
master layer. Retain the ordinary drawing on the corresponding Alternate layer
with both bounds blank (`[]`). Verify which layer supplies each interpolation
set. An Intermediate layer can also be Alternate. Preserve or set its
Intermediate coordinates for the interpolation point and its Alternate bounds
for the active region. Check its correspondence with the set it joins.

Glyphs normally generates GSUB Feature Variations under `rlig` for Alternate
layers in a variable export. Inspect the existing font-level
`Feature for Feature Variations` parameter and use the effective feature in
proofs. Preserve the existing setting unless the task calls for changing it.

### Export-time replacement for a specific export

Use a separate alternate glyph compatible across its interpolating masters.
For a named static instance or variable setting that should use the replacement
throughout that export, set `Rename Glyphs` under the identified Font Info
export. Enter one `<base-glyph>=<alternate-glyph>` swap per line. The base
slot receives the alternate drawing and the alternate slot receives the
ordinary drawing. Add `Remove Glyphs` for the leftover alternate slot only
when it should be omitted and the export has no remaining need for that slot.
Check component users, feature classes and lookups, Unicode mapping and export
flags. Preserve both glyphs in variable settings that need runtime switching.

### Explicit alternate glyphs for conditional OpenType substitutions

Use explicit glyphs when the switch needs finer control over regions, feature
behavior or text context. Keep each glyph compatible across its own masters and
include the glyphs needed by the target export. Reuse the
[OpenType feature skill](../glyphs-mcp-opentype-features/SKILL.md) for source and feature checks.
In the appropriate feature, put axis conditions in a variable-only block.
Use the actual four-character axis tags. Comma-separated ranges in one condition
must all match. Review overlapping conditions and the effective lookup order.

```fea
#ifdef VARIABLE
condition <design-min> < <axis-tag> < <design-max>;
sub <base-glyph> by <alternate-glyph>;
#endif
```

Replace every placeholder with the current request's values and glyph names.
When surrounding text determines the choice, use a contextual substitution
such as `sub <preceding-glyph> <base-glyph>' <following-glyph> by <alternate-glyph>;`
in place of the single substitution. Keep only the context the request needs.
Test that earlier lookups supply the expected input glyphs and later lookups
preserve the desired result. For a static instance, use an export-time swap
only if all occurrences should have the replacement. If the static export
must retain the text distinction, keep the needed alternates and arrange
for the contextual lookup to be compiled for that instance.

## Apply in Glyphs 4

Use advertised MCP operations for supported work. In the checked Glyphs MCP
surface, layer inventory exposes special-layer flags and associations, and
closed native actions cover operations such as reinterpolation. Setting
Alternate-layer rules, instance custom parameters and manual feature source
uses native scripting. Explain that gap and check the current capability
catalog. Follow the [native scripting skill](../glyphs-mcp-scripting/SKILL.md)
and its [execution and recovery contract](../glyphs/references/python-scripts.md).
Use the advertised `python_script` with a whole-script entrypoint for
coordinated changes. Preflight the explicit IDs,
expected rules, drawings and settings before the first write. Preserve
unrelated source and re-read the changed owners afterward.

The [Glyphs 4 API notes](references/troubleshooting.md#glyphs-4-native-details)
cover the tested layer attributes and their representation. Confirm UI labels
and selectors against the running build before using a native UI or script
route. For a genuinely unsupported operation, explain the gap and use a
scoped native route under existing task authorization where available, with
its own recovery. Work through stale targets, rejected writes and missing
expected capabilities in the existing lifecycle. Reconcile pending jobs before
touching their targets. Save or publish only within the task's authorization.

## Verify the requested exports

1. Record the source path and saved revision or content hash, Glyphs build and
   exact instance IDs and formats. Use `feature_compile` when feature source
   changed and `font_export` for the actual binaries. Follow the
   [feature compilation](../glyphs/references/feature-compilation.md) and
   [verified export](../glyphs/references/font-export.md) workflows.
   Export from the intended clean saved snapshot and use an authorized proof
   destination for binary inspection.
   If the edit is unsaved, establish an authorized baseline or report that
   export verification of the edit is pending. Record the artifact hashes.
2. For each requested variable export, inspect `fvar`, `avar` if present and
   the relevant GSUB Feature Variations and lookups. Shape the exported font at
   each reachable boundary and immediately below and above it in exported
   coordinates, using distinct representable locations. Test intersections,
   overlaps and combinations where changing one axis takes the location out
   of the region. Report unreachable points at a clipped axis endpoint.
   Check expected glyph IDs and their outlines, including at the boundary.
   MCP's bounded shaping cases compare feature-on/off results. Read the
   returned glyph IDs or independently shape the same binary to verify the
   specific glyph selected.
3. In each affected requested static instance, resolve the glyph selected for
   the character or shaped string and inspect its compiled outline against the
   intended drawing. Check dependent composites or layout where relevant.
   For contextual rules, shape matching and nonmatching text in every
   applicable export, with the intended feature settings, script, language
   and direction. For variable fonts, do this inside and outside the region
   and at its boundaries.
4. Recheck existing switches and unaffected instances or text that could be
   impacted. Compare with the pre-edit source or verified baseline binaries.
   Report the source revision, test coordinates, expected and observed shape,
   contextual controls and any unverified cases.

## References

- The Glyphs 3 tutorial explains the switching model. [Glyphs, Switching shapes](https://glyphsapp.com/learn/switching-shapes)
- The Handbook documents Alternate layers, export replacement and conditional substitutions. [Glyphs Handbook, Switching Shapes](https://handbook.glyphsapp.com/switching-shapes/)
- The conditional feature reference documents conditions and variable-only blocks. [Glyphs Handbook, Conditional Feature Code](https://handbook.glyphsapp.com/layout/conditional-feature-code/)
- For compatibility, mapping, boundaries, lookup order and static and variable export differences, see [Troubleshooting](references/troubleshooting.md).
