---
name: glyphs-mcp-master-compatibility
description: Diagnose and safely repair one Glyphs glyph's interpolation compatibility across master and relevant special layers.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP master compatibility

Make one explicit glyph compatible without guessing correspondence.

## Diagnose

1. Call `get_server_info`, require `data.apiMajor == 2`, resolve one font with
   `list_documents`, and retain its fingerprint.
2. Search `search_knowledge` for current Glyphs interpolation, path direction,
   start nodes, components, anchors, and special-layer rules. Retrieve the
   evidence used with `get_knowledge`.
3. Use `read_document` to resolve the glyph and every interpolation-participating
   layer. Request exact shapes, anchors, ownership, geometry counts,
   `alignment`, bounds, and provenance; exclude backup layers from the
   compatibility set.
4. Use `execute_python(mode="read_only")` when node order, path direction,
   component matching, or native compatibility diagnostics are not fully
   represented. Bound the output to the one glyph.
5. Classify the mismatch as order/phase-only, localized topology difference,
   component mismatch, or ambiguous/manual. Start-node placement is a semantic
   decision; never rotate open paths or choose a landmark without evidence.

## Repair

Use explicit `move`, `set`, or `duplicate` mechanics only when they fully
describe the intended canonical change. Outline node reordering and other
unsupported structural edits belong in
`execute_python(mode="staged_document")`. Preserve topology, node types,
smooth flags, winding, component identity, anchors, and non-target metadata
unless the user explicitly approves otherwise.

Master duplication and materialization must retain fractional widths,
coordinates, anchors, and component transforms in existing and newly created
layers. Use `duplicate` for a master source and `materialize` for a static
instance source, always with the final `newId`. A master identity is an
ownership root: never rename it after dependent layers exist. Require baseline
and after `observation.masterLayerCoverage.violationCount == 0`, then verify
source and target widths, origins, `observation.geometry.counts`, components,
anchors, metrics keys, and topology exactly; layer existence alone is
insufficient.
Never round or grid-snap them, and never change the grid, subdivision, or
global automatic-alignment setting; the v2
runtime manages its temporary precision state centrally. It owns grid zero
through settlement of every direct and transitive component dependency,
restores the exact entry grid and subdivision before read-back, and isolates an
explicit reviewed grid edit afterward. Agents and scripts must never edit grid
settings to implement this policy.

Create `preview_change` when generic operations suffice. Inspect the immutable
preview, its exact layer identities, before/after
constraints, and semantic diff. Apply once through `apply_change`, then re-read
all participating layers and re-run bounded compatibility diagnostics. Report
remaining ambiguity and proof needs. Never call `save_document` automatically.
