---
name: glyphs-mcp-italic-first-pass
description: Prepare a first-pass slant on a disposable or explicitly authorized font.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs-mcp-italic-first-pass

Reuse the verified [$glyphs](../glyphs/SKILL.md) connection, capabilities and
intended `document_id` already in context; do not repeat setup for this skill.
If missing, use [connection setup](../glyphs/references/connection-session.md)
and [document targeting](../glyphs/references/document-targeting.md). Reuse the
ID for reads of the same font; rediscover after `document_not_found` or target
change, not a missing glyph. Never silently substitute another open font.
Each read is fresh; check source/dirty state when preparing edits.

For the typed slant job, prepare with `start_job`, inspect `get_job` until ready, and
review its report before `apply_job`. Application is a reversible live change;
it does not save. Use `accept_job` only when the user's task authorizes saving
the reviewed whole document; it closes the rollback window. Use `discard_job`
for whole-job restoration or cancellation. Native Undo and Redo are grouped per
glyph. Never save merely to satisfy preparation, and never save, export, close,
or overwrite a font unless the user's task authorizes it. Do not retry an
uncertain write or save as a new job; reconcile the existing job identity first.

For a large custom transformation or a reviewed sequence of slant and correction
steps, offer **direct native scripting** under the [shared route and recovery
guide](../glyphs/references/python-scripts.md#choose-the-route). Run the sequence
locally over explicit surfaces with a verified saved baseline and whole-font saved reload.
Specify angle, pivot, width policy, anchor/component handling and master scope;
do not claim the typed slant algorithm or its checks were reproduced. Keep
`slant` for the existing first-pass workflow, and use a disposable copy for
experiments in either route. Confirm interpolation and visual results separately.

Prepare kind="slant" with explicit glyphs, exact master IDs and the requested
angle. Use a disposable copy for exploration. Review the report once; poll with
`include_preview:false`. Check applied/skipped counts, widths, anchors,
component dependencies and native drawing in the examined masters. Hashes do
not prove master compatibility or good interpolation. Optional straight-stem
preservation is a separate explicit choice. Report incomplete proof and needed
designer review. This is a mechanical first pass, not a finished italic.
See [lean first pass](references/lean-v2.md).

[Documentation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set-v2.mdx).
