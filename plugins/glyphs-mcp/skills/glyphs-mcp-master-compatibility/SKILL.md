---
name: glyphs-mcp-master-compatibility
description: Review master-layer correspondence and prepare consistent contour start nodes.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs-mcp-master-compatibility

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

Use kind="start_nodes" for supported consistent contour starts. Review the
prepared landmarks and cyclic shifts before applying. Malformed or unsupported
segments are refused with exact locations; inspect them in Glyphs. Master deletion,
interpolation replacement and topology surgery are native workflows or
reviewed workspace scripts; they are not MCP job kinds.
See [lean correspondence](references/lean-v2.md).

[Documentation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set-v2.mdx).
