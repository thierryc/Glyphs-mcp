---
name: glyphs-mcp-outlines-docs
description: Inspect curves with Curve Inspector and plan supported outline changes.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs-mcp-outlines-docs

For layer identity, advances and bounds, use `read_entities` and the
[native layer read reference](../glyphs/references/layer-reads.md). An
`outlineHash` is a change guard; it does not reveal node/component geometry.
Report unavailable evidence explicitly before choosing a native UI route.

For selection inspection, use the [selection read reference](../glyphs/references/selection-reads.md).
Require `selection.context.v1` in this connection’s negotiated read capabilities.
If unavailable, explain that the private installation needs its bridge, sidecar
and skills updated together; do not substitute an earlier selection workflow.
Recommend the compact object counts; request bounded node details only when
needed. Distinguish empty selections, no Edit View and incomplete evidence.
This read-only workflow needs no job or Save.

Reuse the verified [$glyphs](../glyphs/SKILL.md) connection, capabilities and
intended `document_id` already in context; do not repeat setup for this skill.
If missing, use [connection setup](../glyphs/references/connection-session.md)
and [document targeting](../glyphs/references/document-targeting.md). Reuse the
ID for reads of the same font; rediscover after `document_not_found` or target
change, not a missing glyph. Never silently substitute another open font.
Each read is fresh; check source/dirty state when preparing edits.

Prepare supported work with `start_job`, inspect `get_job` until ready, and
review its report before `apply_job`. Application is a reversible live change;
native Save is acceptance. Use `discard_job` for whole-job restoration or
cancellation. Native Undo and Redo are grouped per glyph. Never save, export,
close, or overwrite a font unless the user's task authorizes it. Do not retry
an uncertain write as a new job; reconcile the existing job identity first.

There is no arbitrary MCP Python or plugin reload. Unsupported edits require
an explicitly authorised native workflow; do not invent an MCP command.

For curvature display, load the [focused Curve Inspector guide](references/curvature-display.md).
Use Reference Inspector to
compare against Last Saved, a Font File, Local Git or Public GitHub. Keep draw
callbacks display-only. Changes labels belong only to the edited occurrence,
never repeated preview glyphs. Native outline visibility must survive startup,
activation, node edits, panning, Undo and Redo. Use kind="start_nodes" or
kind="slant" only for those supported changes; do not invent curve-edit tools.

[Documentation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set-v2.mdx).
