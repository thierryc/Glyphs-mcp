---
name: glyphs-mcp-scripting
description: Use execute_python as the model-visible Glyphs fallback when typed v2 tools cannot express a focused read, document edit, UI task, or external operation; default document edits to detached staged execution and use explicit recovery rules for open-world code.
---

# Glyphs MCP scripting

Use the smallest verified Python fallback that covers the request.

## Core rules

- Prefer a direct typed apply tool or domain skill when it fits. Typed document
  mutations apply first through detached simulation; they do not use review IDs
  or confirmation tokens. Use `execute_python` because those contracts do not fit.
- Resolve stable `documentId` context and the current document fingerprint before mutation.
- Ground unfamiliar GlyphsApp APIs with `docs_search` and focused `docs_get` pages. Target Glyphs 3.5 and 4 unless the user narrows the host.
- Supply a concise `reason`, `intendedEffect`, explicit context, and bounded output. Never claim arbitrary PyObjC code can be safely killed; timeout enforcement is cooperative.
- Never call `exit()`, `quit()`, or `sys.exit()`. Never save, close, install, reload, restart Glyphs, use files or networking, or launch processes unless those effects are explicitly requested and reviewed in `live_open_world` mode.
- Printed output is not mutation proof. Use fingerprints, semantic diffs, read-back verification, audit receipts, and focused post-read tools.

## Execution workflow

1. Call `get_server_info`, `list_open_fonts`, and `get_document_status` as needed, then classify the request as `read`, `document_edit`, or `files_or_external`.
2. Read-only code may execute directly. Inspect `observedDocumentChange` and `scopeViolations`; a read-intent violation is a safety finding.
3. For document edits, call `execute_python` in the default `staged_document` mode with one explicit document and its expected fingerprint.
4. Review the deterministic paginated semantic diff. Staged code runs against
   `GSFont.copy()` without the live `Glyphs` singleton, and its native archive
   delta must match an independent clone receiving the extracted writable
   patch. This is a correctness boundary, not a hostile-code sandbox.
5. Confirm only with `execute_python(reviewId=..., confirm=true)`. The runtime consumes the exact stored code, arguments, context, and code hash and applies the stored patch without rerunning Python.
   Schema-v5 membership and order changes for glyphs, masters, non-master
   layers, instances, features, classes, and prefixes may be confirmed only
   when canonical replay and an independent native-archive comparison both
   prove equivalence. The review retains bounded opaque native evidence for
   added entities; native objects never enter responses, audit, or history.
   Axis lifecycle and specialized Smart/color properties remain unsupported.
6. Use `live_open_world` only for UI state, global Glyphs APIs, unsupported native objects, files, processes, or networking. It requires exact preview and confirmation, creates a private recovery copy, and never claims external effects are transactional.
7. Keep the returned execution ID, after-fingerprint, rollback coverage, and expiry. Do not infer automatic rollback from native undo grouping.

## Rollback workflow

- For `document_inverse` coverage, call `rollback_python_execution` with the execution ID, exact after-fingerprint, `strategy=auto`, and `confirm=true`.
- Later edits, document replacement, restart, expiry, or fingerprint mismatch make automatic rollback stale; never overwrite them.
- For `recovery_only`, use `strategy=open_recovery_copy`. It opens a separate serialized document and never closes or replaces the working document.
- Rollback covers Glyphs document state only. Files, network calls, processes, preferences, saves, and opened or closed documents require compensation or recovery.
- Do not use `glyph.beginUndo()` or `glyph.endUndo()` to determine rollback availability. `layer.beginChanges()`/`layer.endChanges()` may still be paired in `try/finally` for large native layer edits.

## Reusable artifacts

Route Script-menu commands and plug-ins to `glyphs-mcp-development`. Keep live installation and runtime testing as separate, explicit requests.

## Deeper references

- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
- [Safety model](https://github.com/thierryc/Glyphs-mcp/blob/main/content/concepts/safety-model.mdx)
- [Development skill](https://github.com/thierryc/Glyphs-mcp/blob/main/skills/glyphs-mcp-development/SKILL.md)
