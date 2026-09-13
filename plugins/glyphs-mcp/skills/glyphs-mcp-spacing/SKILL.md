---
name: glyphs-mcp-spacing
description: Prepare and review reference-based spacing suggestions with preserved native metrics.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs-mcp-spacing

For read-only layer measurements, use `read_entities` and the
[native layer read reference](../glyphs/references/layer-reads.md). Resolve exact
layer IDs, preserve fractional values and distinguish stored keys from effective
metrics. A measurement request does not need a spacing job or Save.

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

Prepare kind="spacing" with explicit glyphs and optional masters, reference,
references, and widthMode options. Ask whether current metrics are trusted or
placeholders when that affects reference selection. Preserve tabular widths,
marks, metrics keys and native component alignment. The project ignores
translations and width differences at or below 0.001 font units before
preparation; exact application, history and recovery remain exact. Inspect the
effective bearings in the proof. Review HHHOHH, AVAYAW, nonono and mixed text
before accepting suggestions. This is a first pass, not optimal optical spacing.
See [lean spacing](references/lean-v2.md) for the supported options.

[Documentation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set-v2.mdx).
