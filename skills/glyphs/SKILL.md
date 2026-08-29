---
name: glyphs
description: Use this skill as the general Glyphs MCP entry point for inspecting or editing an open Glyphs font, gathering evidence, or routing to focused type-design expertise.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP

Use Knowledge for facts, focused skills for judgment, and generic tools for mechanics.
Generic Python with no Glyphs app or font target does not trigger this skill.

## Core workflow

1. Call `get_server_info`; require `data.apiMajor == 2` and inspect the entity,
   projection, operation, Knowledge, and permanent Python capabilities.
2. Resolve one stable font with `list_documents`. Use `read_document` with an
   exact `EntitySelector` and the smallest useful `Projection`; retain the
   document fingerprint and follow selector-owned pagination.
3. Use `search_knowledge` when a design, engineering, Glyphs API, scripting, or
   file-format fact affects the decision. Retrieve selected evidence with
   `get_knowledge` and retain its citation and version scope.
4. Make typographic choices in the applicable focused skill. Tools must not be
   treated as sources of design policy.
5. When a requested edit is mechanically expressible, create explicit `set`,
   `translate`, `insert`, `remove`, `move`, or `duplicate` operations and
   before/after constraints. Call `preview_change`, explain the immutable
   semantic patch, then apply its exact `previewId` once with `apply_change`.
6. When the typed surface is insufficient, use the permanent `execute_python`
   fallback: `read_only` for bounded inspection, `staged_document` for detached
   edits applied through `apply_change`, and `live_open_world` only for explicit
   unsupported UI, file, process, or other external effects.
7. Re-read affected entities, inspect `list_history` or `get_operation` when
   needed, and use `revert_change` for a compatible unsaved-session reversal.
   Never save unless the user separately requests `save_document`.

The user may save in Glyphs between any two actions. Treat that as normal
persistence concurrency: only a changed live canonical fingerprint stales a
preview. `apply_change` reconciles saved-before, saved-after, or intermediate
states and reports residual unsaved work. Never prevent, undo, or repeat a Save.
Keep `expectedDocumentFingerprint`, `expectedSourceFileFingerprint`, and
`expectedDestinationFileFingerprint` distinct; only `save_document` protects
file overwrites.

Incomplete observations are evidence gaps, not passes. Locks and alignment are
preserved state, not policy failures. Structural invalidity, stale live state,
and failed read-back are hard failures. Source drift may warn but never blocks
later document work.

## Focused expertise

Route spacing to `glyphs-mcp-spacing`, kerning to `glyphs-mcp-kerning`, outlines to
`glyphs-mcp-outlines-docs`, compatibility to `glyphs-mcp-master-compatibility`, and OpenType
to `glyphs-mcp-opentype-features`; use the Unicode/icon, variable/color/export
corresponding audit skill. Route Python to `glyphs-mcp-scripting`; Reusable scripts and plug-ins to `glyphs-mcp-development`.
