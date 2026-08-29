---
name: glyphs-mcp-export-validation
description: Validate Glyphs source export readiness or existing font binaries with explicit evidence levels, skips, and cited version-aware checks, without exporting implicitly.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP export validation

Classify the task as source readiness, existing-binary validation, or both.

## Workflow

1. Call `get_server_info`, require `data.apiMajor == 2`, and resolve one source
   with `list_documents` when a live Glyphs document is in scope.
2. Search `search_knowledge` for the relevant Glyphs export, OpenType, variable,
   color, and file-format requirements. Retrieve decisive entries with
   `get_knowledge` and record their Glyphs-version scope.
3. Use `read_document` for axes, masters, instances, glyph coverage, features,
   metrics, special layers, and detached `compilation.diagnostics`. Route
   typographic interpretation to the focused domain skills.
4. Use `preview_export` for a deterministic source-bundle preflight. It is
   evidence, not authorization to publish files. Call `apply_export` only when
   the user explicitly requests that exact previewed external effect.
5. For existing binaries, inspect only user-supplied artifacts. Run available
   sanitizers and target profiles; label unavailable tools, platforms,
   baselines, or test fonts as `SKIP`, never `PASS`.
6. Re-read the live document fingerprint after read-only validation. Do not apply
   document changes or call `save_document` as part of validation.

Use [the export-validation reference](references/export-validation.md) for
naming, linking, cmap/tables, metrics, variation data, and regressions. Report
source evidence, binary evidence, visual evidence, blockers, warnings, skips,
citations, and reproducible commands separately.
