---
name: glyphs-mcp-development
description: Create, extend, or review reusable workspace-first Glyphs Python scripts and plug-ins from pinned APIs and SDK templates.
metadata:
  surface: glyphs-mcp-v2
---

# Glyphs MCP development

Create workspace artifacts; do not install or execute them implicitly.

## Evidence and architecture

1. Before using the live plugin, call `get_server_info` and require
   `data.apiMajor == 2`. Workspace-only scaffolding may proceed without a live
   server but must not invent a callable tool.
2. Use `search_knowledge` and `get_knowledge` for versioned Glyphs scripting,
   plug-in APIs, SDK templates, and compatibility notes. The pinned local SDK
   may supply complete templates and files; record its revision.
3. Use `read_document` for live canonical context. Use
   `execute_python(mode="read_only")` only to verify a bounded unfamiliar API.
   A requested live test or edit follows `glyphs-mcp-scripting`, with detached
   document patches applied through `apply_change`.
4. Target Glyphs 3.5 and 4 unless the user narrows the versions. Keep native
   compatibility notes explicit.

## Workspace rules

- Determine script versus general, reporter, filter, palette, select-tool, or
  file-format plug-in. Resolve name, purpose, class, developer, and destination.
- Create files in the workspace. Never overwrite an existing artifact or write
  to live Scripts/Plugins folders without a separate explicit request.
- Keep the SDK's `Contents/MacOS/plugin` and Apache attribution unchanged.
- Keep Reporter callbacks drawing-only. Separate reusable logic from Glyphs UI
  glue and isolate version-specific API branches.
- Run `scripts/scaffold.py create` and `scripts/scaffold.py validate <artifact>
  --target both`; static validation is not a live Glyphs test.

When changing this repository's v2 runtime, preserve the hard-reset layering:
Knowledge owns pinned facts, skills own typographic workflows, and the public
tool catalog stays limited to generic reads, constraints, previews, writes,
history, Knowledge, permanent Python, export/save, UI, and runtime repair.
Add mechanics through the shared registries and transaction kernel instead of
adding domain workflow endpoints. Keep schemas single-source and generated,
run the v2 contract/bundle tests, and sync packaged skill mirrors.

Keep floating-point precision adapter-owned and plugin-wide. All geometry-
capable declarative, structural, transaction, staged-Python, and live-Python
paths must use the central nest-safe scope, exact-only quantization, and exact
fractional read-back. Feature-detect `GSLayer.temporarilyDisableRounding`;
use temporary grid zero only for structural/Python execution or as its fallback,
and restore grid, subdivision, global automatic alignment, layer flags, and
update suspension on every exit. Never add local coordinate rounding, grid
snapping, epsilon-to-integer cleanup, or tool-specific precision toggles.

Do not encode workflow policy as mutation guards. Locks, component alignment
configuration, glyph categories, and other design metadata are preserved by
generic operations. The detached native result is the preview; constraints,
exact live read-back, and rollback provide the generic safety boundary. Native
rounding cannot replace a requested fractional effect or turn it into a no-op.
Use
permanent Python fallback instead of adding a task-specific public tool.

Keep live-document atomicity separate from persistence. Native Glyphs Save is
always available and may overlap any tool action; it is evidence to reconcile,
not a transaction blocker or incident. A save-only file change must not stale
an immutable preview. Keep file overwrite protection exclusively in
`save_document`, with document, source-file, and destination-file fingerprints
named and compared independently.

Never install, reload, restart Glyphs, run the artifact, mutate a document,
export, or call `save_document` without the user's separate request. Report
paths, cited APIs, SDK revision, validation, and remaining manual tests.

Use the catalog returned by `get_server_info` as the live command contract and
the local `scripts/scaffold.py` helper for reusable artifacts.
