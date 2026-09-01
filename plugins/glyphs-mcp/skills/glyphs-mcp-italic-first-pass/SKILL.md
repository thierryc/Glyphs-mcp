---
name: glyphs-mcp-italic-first-pass
description: Create a guarded experimental italic or oblique construction draft from Roman glyphs for explicit designer review.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP italic first pass

A mechanical construction is a draft, never a finished italic.

## Evidence and judgment

1. Call `get_server_info`, require `data.apiMajor == 2`, resolve one font with
   `list_documents`, then search `search_knowledge` for current Glyphs slant,
   transform, component, and italic-angle behavior. Retrieve the cited entries
   you rely on with `get_knowledge`.
2. Use `read_document` to resolve exact Roman source masters, italic target
   masters, glyphs, layers, bounds, ownership, geometry counts, components,
   anchors, alignment, and compatibility evidence.
3. Default the Glyphs source angle to positive 12° only when the user gives no
   angle; exported `slnt` and `post.italicAngle` normally use the opposite sign.
   Calculate the shear around an explicit pivot and state whether advance,
   origin, sidebearings, or optical centering is intended to remain fixed.
4. Never overwrite a developed italic. Targets must be empty or explicitly
   approved bootstrap copies. Preserve topology, live components, anchors, and
   non-target metadata; refuse ambiguous component chains or correspondences.

## Construction lifecycle

Build the complete pass as one declarative `preview_change` transaction:

1. Use consecutive generic `duplicate` operations for every target master.
   Give each duplicate its final identity, name, collection index,
   `italicAngle`, and axis coordinates. A master duplicate owns every master
   layer plus LTR, RTL, vertical, and contextual kerning.
2. Use generic `move` and `set` operations only for final order or canonical
   values not already supplied by duplicate overrides.
3. Apply one generic `transform` to the exact target layers. For a baseline
   shear use matrix `[1, 0, tan(angle), 1, 0, 0]`, `origin=[0, 0]` (or
   the designer-approved baseline pivot), `include=[paths, anchors,
   components]`, `componentComposition=conjugate`, and
   `alignmentPolicy=explicit_noncommuting`, with `quantizer=exact` (the
   default). Preserve fractional shear results exactly; do not round or snap
   coordinates, change the grid, or change global automatic alignment. The
   runtime manages precision centrally. Component alignment overrides remain
   explicit opt-ins such as this reviewed noncommuting transform.
4. Add after-constraints for master order and locations, layer coverage,
   widths/origins, topology, compatibility, component references, alignment,
   and kerning. Use semantic verification unless the user explicitly requests
   the slower `strict_archive` diagnostic gate.
5. Apply that immutable preview once through `apply_change`. Snapshot-backed
   recovery is exceptional: it requires a preview created with
   `transactionMode=snapshot_backed_recovery` and an explicit
   `confirmRecovery=true` on apply. An indeterminate document is quarantined;
   stop editing and follow the returned recovery instructions.

Use `execute_python(mode="staged_document")` only when a required construction
cannot be represented by `duplicate`, `move`, `set`, and `transform`. State the
unsupported capability before falling back and retain the same exact scope and
postconditions. Do not use staged Python merely to make a large affine batch.

After application, use `read_document` to inspect the exact layers and proof
strings. Check overshoot, rhythm, joins, counters, diagonals, punctuation,
marks, components, interpolation, and spacing. Report the angle, pivot,
translated distances, `stageTimings`, equivalence evidence, normalized numeric
deltas, rollback classification, exceptions, and limitations. Never call
`save_document` automatically.
