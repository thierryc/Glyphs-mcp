---
name: glyphs-mcp-production-audit
description: Coordinate a read-only production audit from one live document fingerprint by routing to focused Glyphs MCP expertise and aggregating blockers and gaps.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP production audit

Coordinate evidence; do not duplicate each domain's judgment.

## Workflow

1. Call `get_server_info`, require `data.apiMajor == 2`, resolve one font with
   `list_documents`, and retain the starting fingerprint.
2. Use `read_document` only far enough to identify applicable axes, masters,
   instances, glyph coverage, OpenType, color, variable, spacing, kerning,
   Unicode, outline, and export domains. Follow selector-owned pagination and
   record partial projections.
3. Search `search_knowledge` for target- and version-specific requirements;
   retrieve decisive entries with `get_knowledge`.
4. Route detailed evidence and judgment to the applicable focused skills:
   Unicode semantics, color, variable fonts, OpenType, interpolation,
   outlines/anchors, spacing, kerning, and export validation.
5. Use `execute_python(mode="read_only")` only when a focused audit requires a
   bounded native observation that generic projections cannot supply. Treat
   observed mutation as a failed audit.
6. Re-read the fingerprint at the end. Do not call `preview_change`,
   `apply_change`, `apply_export`, or `save_document` during coordination.

Aggregate each domain as PASS, WARN, FAIL, or SKIP with evidence IDs,
citations, affected entities, coverage, and next action. A PASS requires
complete evidence for the stated scope; missing binaries, platforms, tools,
or native observations are SKIP or WARN, never an inferred pass.
