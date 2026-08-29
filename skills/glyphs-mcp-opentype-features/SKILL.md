---
name: glyphs-mcp-opentype-features
description: Inspect, reason about, compile-check, or safely change Glyphs OpenType features, classes, prefixes, stylistic sets, and character variants.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP OpenType features

Keep authored source, detached compilation evidence, live compilation, and
exported binary behavior separate.

## Workflow

1. Call `get_server_info`, require `data.apiMajor == 2`, resolve one font with
   `list_documents`, and retain its fingerprint.
2. Search `search_knowledge` for current Glyphs feature syntax, API behavior,
   Adobe feature-file semantics, and the relevant OpenType tables. Retrieve
   decisive entries with `get_knowledge`.
3. Use `read_document` with `feature`, `class`, and `prefix` selectors to inspect
   ordered canonical source, automatic/disabled state, labels, and notes.
   Request `compilation.diagnostics` on the document for a detached compile
   check. A failed compile is complete failure evidence, not an incomplete read.
4. Parse stylistic-set, character-variant, substitution, positioning, and
   contextual behavior in the skill. Report unsupported or ambiguous source
   constructs without silently simplifying them.
5. Express exact collection edits with generic `insert`, `set`, `move`, and
   `remove` operations plus before/after constraints. Call `preview_change`,
   inspect ordering and semantic diff, then apply the exact preview once with
   `apply_change`.
6. Use `execute_python(mode="read_only")` for bounded native inspection that is
   absent from projections. Use `staged_document` for unsupported source edits.
   A live `compileFeatures()` request is an explicit UI/native effect and
   belongs in `live_open_world` with recovery reporting; it must not save.
7. Re-read source and detached compilation diagnostics after a change. Never
   call `save_document`, export, or claim binary behavior without separate
   shaping/table evidence.
