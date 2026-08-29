---
name: glyphs-mcp-color-font
description: Audit Glyphs color-font sources, including palette, SVG, bitmap, fallback, and export evidence, without editing or saving the font.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP color-font audit

Keep source intent, compiled-table proof, and visual proof separate.

## Evidence workflow

1. Call `get_server_info`, require `data.apiMajor == 2`, then resolve one font
   with `list_documents`.
2. Use `search_knowledge` for current Glyphs color-layer APIs, COLR/CPAL, SVG,
   sbix, CBDT/CBLC, and export limitations; retrieve decisive entries with
   `get_knowledge`.
3. Use `read_document` to inspect exact masters, glyphs, layers, ownership,
   attributes, shapes, and fallbacks. Request provenance and treat partial
   projections as coverage gaps.
4. When palette or native color attributes are absent from canonical reads,
   use bounded `execute_python(mode="read_only")`. Reject any observed mutation.
5. If source-bundle readiness matters, use `preview_export`; do not call
   `apply_export` unless the user separately requests the external file effect.
6. Re-read the document fingerprint at the end. Do not preview a document
   mutation, apply, export, or call `save_document` during an audit.

Read [the color-font audit reference](references/color-font-audit.md) for
mechanism-specific checks. Never claim compiled COLR, CPAL, SVG, sbix, CBDT,
or CBLC tables pass without inspecting an existing compiled binary.

Report mechanisms, coverage, palette evidence, fallback behavior, blockers,
warnings, skipped checks, citations, and the exact evidence boundary.
