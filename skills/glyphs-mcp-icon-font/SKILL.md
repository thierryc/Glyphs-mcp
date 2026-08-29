---
name: glyphs-mcp-icon-font
description: Audit, allocate, compare, or safely change stable Unicode and PUA assignments in icon or symbol fonts.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP icon font

Use this skill for encoding stability, not icon drawing.

## Workflow

1. Call `get_server_info`, require `data.apiMajor == 2`, resolve one font with
   `list_documents`, and retain its fingerprint.
2. Use `search_knowledge` for the Unicode/PUA version and semantics in scope;
   retrieve decisive entries with `get_knowledge`.
3. Use paginated `read_document` glyph selectors to inspect exact names,
   Unicode values, export state, categories, and requested layer evidence.
4. Preserve existing assignments. For a released font, require the previous
   mapping before allocating; otherwise audit only unless the user explicitly
   authorizes a new baseline. Never infer standard Unicode from an icon name or
   drawing. Default private icon allocation to BMP PUA unless told otherwise.
5. Present collisions, reserved values, range capacity, and the exact proposed
   glyph-to-codepoint map.
6. For an authorized mapping, express each value as an explicit `set` operation
   on an exact glyph selector, add before/after constraints, and call
   `preview_change`. Apply the immutable preview once with `apply_change`.
7. Re-read every changed mapping and use `list_history` or `get_operation` for
   the verified receipt. Never call `save_document` automatically.

Use `execute_python(mode="read_only")` only when canonical reads cannot expose
required native metadata. Use `staged_document` for an unsupported requested
document edit and still apply it through `apply_change`; never use Python to
bypass the preview lifecycle.
