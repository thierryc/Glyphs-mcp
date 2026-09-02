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
   you rely on with `get_knowledge`. Inspect the generic mechanics registry: if
   an instance must become a master and `materialize` is not advertised for
   instances, classify runtime/deployment skew and stop before mutation rather
   than improvising a live bootstrap.
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

1. Use one consecutive leading batch of source-correct master operations. Use
   `duplicate` when the source is an existing master and `materialize` when the
   source is an interpolated static instance. Give every operation its final
   `newId`, name, collection index, `italicAngle`, and axis coordinates. A
   master identity is an ownership root, not a mutable label: never attach a
   master under a temporary ID and rename it after Glyphs has created dependent
   layers. Both operations own every resulting master layer plus LTR, RTL,
   vertical, and contextual kerning.
2. Use generic `move` and `set` operations only for final order or canonical
   values not already supplied by operation overrides. Never use them to
   change an attached master identity.
3. Apply one generic `transform` to the exact target layers. For a baseline
   shear use matrix `[1, 0, tan(angle), 1, 0, 0]`, `origin=[0, 0]` (or
   the designer-approved baseline pivot), `include=[paths, anchors,
   components]`, `componentComposition=conjugate`, and
   `alignmentPolicy=explicit_noncommuting`, with `quantizer=exact` (the
   default). Preserve fractional shear results exactly; do not round or snap
   coordinates, change the grid, or change global automatic alignment. The
   runtime manages precision centrally: it owns grid zero through direct and
   transitive component settlement, restores the exact entry grid and
   subdivision before read-back, and isolates explicit reviewed grid edits
   afterward. Agents and scripts must never edit grid settings to implement
   this policy. Component alignment overrides remain explicit opt-ins such as
   this reviewed noncommuting transform.
4. Add before- and after-constraints requiring
   `observation.masterLayerCoverage.violationCount == 0`; do not use master
   creation as an implicit repair for a faulty starting structure. For every
   ordinary glyph this proves that canonical master-layer identities equal the
   font master identities, each owner occurs exactly once in the reserved
   master-layer prefix,
   `layer.id == layer.masterId == master.id`, and no layer references an
   unknown master. Derive expected counts from the baseline and requested
   additions; never hard-code a specimen's master or glyph count.
5. Before any transform can become applicable, add exact source/target field
   constraints for width and origin plus `observation.geometry.counts`; inspect
   paths, nodes, components, anchors, component references and transforms,
   metrics keys, topology, compatibility, and kerning. Layer existence alone
   is not evidence that native materialization preserved content. Use semantic
   verification unless the user explicitly requests the slower
   `strict_archive` diagnostic gate.
6. Apply that immutable preview once through `apply_change`. Snapshot-backed
   recovery is exceptional: it requires a preview created with
   `transactionMode=snapshot_backed_recovery` and an explicit
   `confirmRecovery=true` on apply. An indeterminate document is quarantined;
   stop editing and follow the returned recovery instructions.

Use `execute_python(mode="staged_document")` only when a required construction
cannot be represented by `duplicate`, `materialize`, `move`, `set`, and
`transform`. State the unsupported capability before falling back and retain
the same exact scope and postconditions. Missing mechanics in a stale runtime
are deployment skew, not permission for a live fallback. Do not use staged
Python merely to make a large affine batch.

After application, use `read_document` to inspect the exact layers and proof
strings. Check overshoot, rhythm, joins, counters, diagonals, punctuation,
marks, components, interpolation, and spacing. Report the angle, pivot,
translated distances, `stageTimings`, equivalence evidence, normalized numeric
deltas, rollback classification, exceptions, and limitations. Never call
`save_document` automatically.
