---
name: glyphs-mcp-kerning
description: Discover native kerning groups and stored pairs, inspect exact values, and review collision repairs.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs-mcp-kerning

For unknown group assignments or stored pairs, use [kerning discovery](../glyphs/references/kerning-discovery.md). Require the matching private capability; reuse connection/document context and request only needed fields. Discovery needs no job.


Reuse the verified [$glyphs](../glyphs/SKILL.md) connection, capabilities and
intended `document_id` already in context; do not repeat setup for this skill.
If missing, use [connection setup](../glyphs/references/connection-session.md)
and [document targeting](../glyphs/references/document-targeting.md). Reuse the
ID for reads of the same font; rediscover after `document_not_found` or target
change, not a missing glyph. Never silently substitute another open font.
Each read is fresh; check source/dirty state when preparing edits.

For stored-value inspection, follow the [kerning read reference](../glyphs/references/kerning-reads.md).
Read exact glyph-name or established group-key pairs on dirty or unsaved fonts;
no Save, job or external script is needed. Pure inspection stops after reporting
the stored evidence. It does not imply a collision-repair request.

Only when collision repair is requested, verify `kerning_collision` in this
connection’s `jobKinds`. If unavailable, the installation needs updating: update
the bridge, sidecar and skills together; do not use an earlier private fallback.
Prepare supported work with `start_job`, inspect `get_job` until ready, and
review its report before `apply_job`. Application is a reversible live change;
native Save is acceptance. Use `discard_job` for whole-job restoration or
cancellation. For collision jobs, native Undo/Redo belongs to the left glyph's
Edit-view history; it is not whole-job restoration. See the focused reference
for the tested scope and sampling limits. Never save, export,
close, or overwrite a font unless the user's task authorizes it. Do not retry
an uncertain write as a new job; reconcile the existing job identity first.

There is no arbitrary MCP Python or plugin reload. Unsupported edits require
an explicitly authorised native workflow; do not invent an MCP command.

Prepare kind="kerning_collision" with explicit pairs and master scope. Inspect
pair clearance, existing kerning and the suggested corrections in the report.
Preserve existing classes and exceptions unless explicitly targeted. Review
proof strings before acceptance; collision avoidance is not optical kerning.
See [lean kerning](references/lean-v2.md).

[Documentation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set-v2.mdx).
