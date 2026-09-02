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

1. Call `get_server_info`; require `data.apiMajor == 2` and inspect the generic
   registries, Knowledge, and permanent Python capabilities.
2. Resolve one stable font with `list_documents`. Use `read_document` with an exact
   `EntitySelector` and minimal `Projection`; retain its fingerprint and pagination.
3. Use `search_knowledge` when a design, engineering, Glyphs API, scripting, or
   format fact affects the decision; retrieve cited evidence with `get_knowledge`.
4. Make typographic choices in the applicable focused skill, not in tools.
5. Express edits as explicit generic operations and constraints. Call
   `preview_change`, explain the immutable patch, then apply its exact `previewId`
   once with `apply_change`.
6. When typed mechanics are insufficient, use the permanent `execute_python` fallback:
   `read_only` for inspection, `staged_document` for detached edits applied through
   `apply_change`, and `live_open_world` only for explicit external effects.
7. Re-read affected entities; use `list_history`, `get_operation`, and compatible
   `revert_change` as needed. Save only when separately asked via `save_document`.

The user may save between actions. Only a changed live canonical fingerprint stales
a preview; never prevent, undo, or repeat a Save. Keep document, source-file, and
destination-file fingerprints distinct; only `save_document` protects overwrites.

Incomplete observations are evidence gaps, not passes. Locks and alignment are
preserved state. Structural invalidity, stale state, and failed read-back are hard failures.

Geometry is floating-point and exact-only. Preserve every nonzero fraction; never
round or grid-snap coordinates, change the grid/subdivision, or change global
automatic alignment. The runtime owns precision and fails closed when unavailable;
component alignment changes remain explicit opt-ins.
For direct or dependency-induced component geometry, the runtime snapshots `font.grid` and `gridSubDivision`, owns grid zero through transitive component settlement, restores exact entry settings before read-back, and isolates reviewed grid edits afterward.
Agents and scripts must never implement this policy by editing grid settings themselves.

Registered non-rounding native effects can be review items when evidence is complete
and the edit is verified and reversible; unregistered geometry deviation is a blocker.
Never apply an inapplicable preview or continue through failed recovery or data-loss risk.

## Focused expertise

Route spacing to `glyphs-mcp-spacing`, kerning to `glyphs-mcp-kerning`, outlines to
`glyphs-mcp-outlines-docs`, compatibility to `glyphs-mcp-master-compatibility`, and
OpenType to `glyphs-mcp-opentype-features`; use the corresponding audit skill for
Unicode/icon, variable/color, or export work. Route Python to `glyphs-mcp-scripting`.
Reusable scripts and plug-ins route to `glyphs-mcp-development`.
