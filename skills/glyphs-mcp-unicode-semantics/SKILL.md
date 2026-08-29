---
name: glyphs-mcp-unicode-semantics
description: Audit Unicode mappings and semantic glyph behavior, including controls, whitespace, marks, PUA use, normalization, and .notdef, without editing.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP Unicode semantics audit

Do not confuse glyph name, blank outline, or zero advance with character
semantics.

## Workflow

1. Call `get_server_info`, require `data.apiMajor == 2`, resolve one font with
   `list_documents`, and retain its fingerprint.
2. Search `search_knowledge` for the Unicode version, default ignorables,
   normalization, cmap behavior, and Glyphs Unicode APIs in scope. Retrieve
   decisive entries with `get_knowledge`.
3. Use paginated `read_document` glyph selectors for mappings, names, export
   state, categories, scripts, and metadata. Read exact layers with advances,
   bounds, shapes, components, and ownership across every relevant master and
   special layer.
4. Apply [the semantic-glyph reference](references/unicode-semantic-glyphs.md).
   Classify `.notdef`, spaces, controls, joiners, variation selectors, marks,
   default ignorables, soft hyphen, PUA, duplicates, and normalization
   sequences by semantics rather than name.
5. Use `execute_python(mode="read_only")` only for bounded Unicode/native data
   absent from projections. Do not use it to simulate shaping.
6. Re-read the source fingerprint. Do not call `preview_change`,
   `apply_change`, `apply_export`, or `save_document` in this audit.

A mapped U+00AD with contours, components, or nonzero advance is normally a
release blocker for a modern text font, but report the product context and
cited standard. Route icon PUA allocation to `glyphs-mcp-icon-font` and feature
implementation to `glyphs-mcp-opentype-features`.
