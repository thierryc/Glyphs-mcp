---
name: glyphs-mcp-master-compatibility
description: Diagnose and safely repair one Glyphs glyph's interpolation compatibility across master and relevant special layers; use for full compatibility work, not an already-compatible path's start-node-only alignment.
---

# Glyphs MCP master compatibility

Make one selected or explicitly named glyph compatible without forcing an
unsafe correspondence.

## Core rules

- Work on one glyph at a time. Resolve a stable `documentId`, the starting
  document fingerprint, the target glyph, and its interpolation-participating
  master and special layers. Ignore backup layers.
- Diagnose before editing with `review_master_compatibility`; follow paginated
  findings with `get_operation`. Read detailed paths, components, anchors, and
  the host-derived `mastersCompatible` value with `list_glyphs`,
  `get_glyph_details`, `get_glyph_paths`, and `get_glyph_components` when those
  dedicated reads are available.
- Use bounded read-intent `execute_python` only when dedicated reads cannot
  expose the comparison detail. Treat any observed mutation as a failed read.
- Classify mismatches before proposing a repair: order/phase-only, nearly
  compatible with one localized topology difference, or ambiguous/manual.
- For each corresponding closed-path set, make semantic start-node placement
  the first repair attempt. Use `review_start_node_alignment` followed by
  fingerprint-bound `apply_start_node_alignment`; never rotate open paths or
  guess an ambiguous landmark.
- Preserve coordinates and every non-target node field during ordering,
  direction, or start-node repairs. Never use destructive simplification merely
  to obtain compatibility.
- Before adding an off-curve node, or changing a line to a curve in a way that
  introduces handles, report the exact glyph, master, path, segment, proposed
  node sequence, and reason, then stop for explicit permission.
- Use `apply_compatibility_updates` only for explicit, reviewed path or
  component repairs. If the typed surface cannot express a narrow safe edit,
  use `execute_python` in `staged_document` mode, present its semantic diff,
  and stop before confirmation.
- Never auto-save the font.

## Workflow

1. Read the target and record the initial `mastersCompatible` state and
   fingerprint. Multiple named glyphs are independent runs.
2. Run the host review, then read the detailed structures needed to compare
   shape order, paths, nodes, components, and anchors.
3. Read [the compatibility playbook](references/compatibility-playbook.md) and
   follow its diagnostic matrix and repair order.
4. Apply only unambiguous repairs. For staged Python, confirm only the stored
   review ID and exact code after the user approves its diff.
5. Re-read every affected layer, rerun `review_master_compatibility`, and read
   the authoritative host-derived `mastersCompatible` value again.
6. Report success only when `mastersCompatible == true`. If it remains false,
   report the remaining evidence and exact manual directions; never claim the
   glyph is compatible.

Technical compatibility does not prove good interpolation. Flag crossing
correspondences or other likely shape-shifters and direct the user to **View >
Show Master Compatibility** for visual review.

## Deeper references

- [Compatibility playbook](references/compatibility-playbook.md)
- [Glyphs Handbook: Outline Compatibility](https://www.handbook.glyphsapp.com/interpolation/outline-compatibility/)
- [Glyphs tutorial: Keeping Your Outlines Compatible](https://glyphsapp.com/learn/multiple-masters-part-2-keeping-your-outlines-compatible)
- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
