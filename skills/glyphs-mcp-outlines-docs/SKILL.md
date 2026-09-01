---
name: glyphs-mcp-outlines-docs
description: Inspect or safely edit Glyphs outlines, components, anchors, selected nodes, cubic geometry, curvature, and related native APIs.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP outlines and anchors

Use measurements as evidence, not artistic scores.

## Workflow

1. Call `get_server_info`, require `data.apiMajor == 2`, resolve one font with
   `list_documents`, and retain its fingerprint.
2. Search `search_knowledge` for the applicable Glyphs path/node/component/
   anchor APIs, cubic geometry, path direction, and interpolation rules.
   Retrieve decisive entries with `get_knowledge`.
3. Use `read_document` to resolve exact glyph, layer, shape, and anchor
   identities. Request canonical geometry, `bounds`, `geometry.counts`,
   `alignment`, ownership, and provenance.
4. Use `execute_python(mode="read_only")` for selected nodes, handle geometry,
   Tunni balance, extrema, curvature, or native details absent from projections.
   Bound inspection to named entities and reject observed mutation.
5. Preserve topology, node types, smooth flags, winding, component identity,
   anchors, layer metadata, and non-target attributes unless the user approves
   a stated change. Never rotate an open path or guess an ambiguous match.

Generic `translate` moves paths, components, and anchors uniformly on an exact
layer. Generic `insert`, `set`, `move`, and `remove` cover explicit canonical
shape/anchor mechanics when their full values are known. Node-level and other
unsupported edits use `execute_python(mode="staged_document")`.

Preserve fractional node, anchor, component, width, and transform values
exactly. Do not round coordinates, snap to the font grid, change the grid or
subdivision, or change global automatic alignment; the v2 runtime manages
precision centrally. Component-level alignment changes require an explicit,
reviewed alignment policy.

Always add physical before/after constraints, inspect the immutable
`preview_change` or staged Python preview, and apply it only through
`apply_change`. Re-read exact affected entities and proof interpolation,
spacing, component alignment, and curve continuity. Never call
`save_document` automatically.
