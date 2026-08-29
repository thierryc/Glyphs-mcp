---
name: glyphs-mcp-litsquare-metadata
description: Inspect, explain, preview, and safely change LitSquare userData and semantic path-role metadata in Glyphs.
metadata:
  surface: glyphs-mcp-v2
---

# LitSquare metadata for Glyphs MCP

Treat native `userData` dictionaries and path `attributes` as authoritative;
JSON is only a bounded projection. Read
[the metadata contract](references/metadata-contract.md) before recommending a
mutation.

## Workflow

1. Call `get_server_info`, require `data.apiMajor == 2`, resolve one font with
   `list_documents`, and retain its fingerprint.
2. Use `search_knowledge` for relevant Glyphs userData, layer, path, selection,
   and scripting APIs; retrieve decisive entries with `get_knowledge`.
3. Use `read_document` to resolve exact glyph/layer/shape identities,
   ownership, attributes, and canonical metadata. Distinguish missing,
   explicit null, inherited, mixed, and unrepresentable values.
4. For effective inheritance or current UI selection not exposed by generic
   projections, use a minimal `execute_python(mode="read_only")` projection.
5. Preserve unrelated dictionary keys, path attributes, native object types,
   and shape order. Interpret roles with the metadata reference; do not infer a
   role solely from bounds or position.
6. Use declarative `set`, `insert`, or `remove` operations when the exact
   canonical path is expressible. Otherwise use
   `execute_python(mode="staged_document")` on exact identities. In both cases,
   inspect an immutable preview and apply it only through `apply_change`.
7. Re-read direct/effective values and every changed path role. Report the
   verified operation and unresolved native values. Never call `save_document`
   automatically.
