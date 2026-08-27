---
name: glyphs-mcp-spacing
description: Review and safely apply the current Glyphs MCP v2 width-only spacing operation, then verify metrics and hand visual proof back with the font unsaved.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP v2 spacing

Use the current typed v2 spacing workflow for advance-width proposals. The
operation does not translate outlines or anchors, does not directly set left or
right sidebearings, and does not promise fractional-coordinate preservation.

## Core rules

- Resolve the exact document with `get_server_info`, `list_open_fonts`, and
  `get_document_status`. Record its stable `documentId` and fingerprint.
- Inspect target glyphs and layers with `list_glyphs` and `list_layers`.
  Review `review_metrics_inheritance` when metrics keys, linked widths, or
  automatic alignment may own the result.
- Call `review_spacing` before mutation with explicit glyph/master items.
  Check bounded convergence, dependencies, proposed widths, skipped targets,
  and automatic-alignment ownership.
- Do not send the removed dry_run argument to `apply_spacing`; v2 uses `review_spacing` for the
  non-mutating preview and a separate direct apply call.
- The current `apply_spacing` operation changes eligible layer widths only.
  Never describe it as translating foreground shapes, anchors, components, or
  sidebearings.
- Do not add or request a `preserveFractionalCoordinates` boolean. Glyphs Grid
  1 behavior must be reproduced first; a later typed operation should
  explicitly define foreground-shape and anchor translation together with the
  width change.
- When the user has clearly authorized the reviewed width edits, call
  `apply_spacing` once with the exact targets, dependencies, fingerprint, and
  reason. It is a direct verified transaction, not a review-token flow.
- Re-read the affected layers and document fingerprint. Never auto-save.

## Workflow

1. Identify the document, masters, target layers, current widths, metrics keys,
   automatic-alignment state, and any width dependencies.
2. Run `review_spacing` and report each target's current/proposed width,
   dependency source, status, and skip reason.
3. Separate eligible width changes from work that requires geometric
   translation or sidebearing judgment. Leave the latter unchanged.
4. After authorization, call `apply_spacing` for eligible width-only changes.
5. Verify the requested and observed changes, operation ID, audit receipt, and
   revert availability.
6. Recommend manual Glyphs proofs appropriate to the glyph set. Computer Use is
   optional; if unavailable or declined, leave the font open and unsaved for the
   user's visual inspection.

## Comparison and proofing

Treat reference-font metrics as evidence, not ground truth. State the source
font, master, and scaling method when comparing widths. Useful proofs include
`HHHOHH`, `HOHOHO`, `AVAYAW`, `JHJOJ`, `nnnon`, `nonono`, repeated
figures, and narrow punctuation beside capitals, lowercase, figures, and spaces.

## Deeper references

- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
- [Safety model](https://github.com/thierryc/Glyphs-mcp/blob/main/content/concepts/safety-model.mdx)
