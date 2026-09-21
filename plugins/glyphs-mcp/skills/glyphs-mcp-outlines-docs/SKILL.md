---
name: glyphs-mcp-outlines-docs
description: Inspect curves and safely prepare typed outline path edits.
metadata:
  surface: glyphs-mcp-v2
---

# glyphs-mcp-outlines-docs

For every outline task, first inspect the current Edit View with compact
`context` and native `selection` summary reads, even when the user supplied
explicit targets. Record whether selection informed the target. Explicit
glyph/layer/path/node targets always win; unrelated selection never retargets a
mutation. Request bounded selected-node details only to resolve an implicit target.

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
it does not save. Use `accept_job` only when the user's task authorizes saving
the reviewed whole document; it closes the rollback window. Use `discard_job`
for whole-job restoration or cancellation. Native Undo and Redo are grouped per
glyph. Never save merely to satisfy preparation, and never save, export, close,
or overwrite a font unless the user's task authorizes it. Do not retry an
uncertain write or save as a new job; reconcile the existing job identity first.

For general path reads and `kind="outline_edit"`, follow the
[typed path-editing workflow](references/path-editing.md). Require
`paths.list.v1`, `path.geometry.v1`, and bridge `writeCapabilities` containing
`outline.edit.v1` before mutation. Resolve explicit native layer IDs, path and
raw node indices, then retain exact returned `pathHash` guards. Reads remain
available on dirty or unsaved fonts; jobs still require a saved clean baseline.
For ordinary node removal, also require `outline.remove-node.v1` and use
`remove_node`; reserve raw `delete_nodes` for explicitly requested topology
surgery because it does not invoke Glyphs' keep-shape behavior.

There is no arbitrary MCP Python or plugin reload. Unsupported edits require
an explicitly authorised native workflow; do not invent an MCP command.

For a complete-target Glyphs command, prefer an advertised closed native
action over scripting. The outline routes are `correct_path_direction`,
`round_coordinates`, `add_extremes`, `cleanup_paths`, `remove_overlap`,
`add_missing_anchors`, `align_components`, `decompose_components`,
`decompose_corners`, `make_components`, `connect_open_paths`, and
`swap_foreground_background`. Follow the
[native-action reference](../glyphs/references/native-actions.md), preserving
its exact layer targeting and action-specific risk review. Do not use these
selection-independently defined actions to emulate a selection-sensitive command.

For curvature display, load the [focused Curve Inspector guide](references/curvature-display.md).
Use Reference Inspector to
compare against Last Saved, a Font File, Local Git or Public GitHub. Keep draw
callbacks display-only. Changes labels belong only to the edited occurrence,
never repeated preview glyphs. Native outline visibility must survive startup,
activation, node edits, panning, Undo and Redo. Use typed `outline_edit`,
`start_nodes`, or `slant` only for their advertised operations; do not invent
curve-edit tools.

[Documentation](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set-v2.mdx).
