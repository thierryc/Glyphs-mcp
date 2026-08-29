---
name: glyphs-mcp-variable-font
description: Audit Glyphs variable-font axes, mappings, masters, instances, special layers, compatibility, and export readiness without repairing or saving.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP variable-font audit

Keep source design-space evidence distinct from compiled variation tables.

## Workflow

1. Call `get_server_info`, require `data.apiMajor == 2`, resolve one font with
   `list_documents`, and retain its fingerprint.
2. Search `search_knowledge` for current Glyphs axes, mappings, origin,
   instances, brace/bracket layers, interpolation, and variable export APIs.
   Retrieve decisive entries with `get_knowledge`.
3. Use `read_document` to inspect axes, masters, instances, exact glyph/layer
   coverage, ownership, interpolation coordinates, geometry counts,
   components, anchors, and compatibility evidence. Follow all pages.
4. Route ambiguous outline compatibility to
   `glyphs-mcp-master-compatibility`. Use
   `execute_python(mode="read_only")` only for bounded native mappings or
   custom parameters missing from canonical projections.
5. Use `preview_export` to inspect source-bundle readiness for the intended
   variable target. Do not call `apply_export` unless the user separately asks
   for that exact external effect.
6. Re-read the source fingerprint. Do not call `preview_change`,
   `apply_change`, or `save_document` during an audit.

Use [the variable-font audit reference](references/variable-font-audit.md) for
axes, mappings, origins, coordinates, instances, special layers, and naming.
Never claim `fvar`, `avar`, STAT, GDEF, GPOS, or variation-outline tables pass
without inspecting an existing compiled binary. Report gaps and skipped proof.
