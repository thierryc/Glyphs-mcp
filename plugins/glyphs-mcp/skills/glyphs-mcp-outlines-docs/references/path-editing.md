# Typed path editing

Require `paths.list.v1` and `path.geometry.v1` in negotiated
`readCapabilities`, plus `outline.edit.v1` in bridge `writeCapabilities` and
`outline_edit` in sidecar `jobKinds`. A missing capability means the bridge,
sidecar and skills must be updated together. The public tool count remains
nine; never substitute arbitrary Python or direct font-file editing.
Shape-preserving removal additionally requires `outline.remove-node.v1`.

Always read compact `context` and `selection` first. State whether selection
informed the target. Explicit user-supplied glyph, layer, path and node targets
take precedence over selection; selection is evidence, never a late-bound write
scope.

Use these sole-selector reads:

- `{"kind":"paths","glyph":"y","layer":"<id>"}` with
  `fields:["items"]`, optional `limit` 1–100 and opaque cursor. Items include
  path/shape indices, open/closed, locked, counts, bounds and `pathHash`.
- `{"kind":"path","glyph":"y","layer":"<id>","index":0}` with
  `fields:["nodes"]`, optional `limit` 1–256 and opaque cursor. Nodes use raw
  zero-based indices and normalized line/curve/qcurve/offcurve types.
- `{"kind":"segment","glyph":"y","layer":"<id>","path":0,
  "endNode":4}` with requested fields among `type`, `startNode`, `endNode`,
  `controlNodes`, `points`, `length`, and `pathHash`.

Pass cursors unchanged. On `stale_path_cursor` or any observed edit, discard
partial pages and restart. Path reads are fresh and bounded, not an atomic
multi-call snapshot. Dirty and unsaved fonts remain readable.

Prepare mutations with `start_job(kind="outline_edit")`. `options.targets`
names an explicit glyph, `referenceLayer`, initial path-hash guards, operations,
and either `layers:{"scope":"all_masters"}` or
`layers:{"scope":"ids","ids":[...]}`. `all_masters` selects ordinary masters
only; brace, bracket and other special layers require exact explicit IDs.
Backgrounds are excluded. Default `compatibilityPolicy` is `preserve`; use
`allow_incompatible` only when the user explicitly requested incompatible
topology and highlight the report warning.

Operations execute in order and subsequent indices address the evolving path:

- `split_segment`: explicit path/start/end raw indices, 1–32 unique fractions,
  default `measure:"arc_length"`; use `path_time` only when explicitly wanted.
- `update_nodes`: unique raw node indices with absolute position or delta and
  optional type, smoothness or name.
- `remove_node`: one explicit on-curve raw index, using Glyphs' native
  shape-preserving Remove Node behavior. Require `outline.remove-node.v1`.
  Ordered removals use evolving indices. Review `removedNodes` and the
  before/after states for surviving handles in each layer's report.
- `delete_nodes`: explicit raw topology deletion. Use it only when the user
  explicitly requests raw node/control surgery; it can change contour geometry
  and therefore adds a preparation warning.
- `reverse_path`, `set_start_node`, and `set_closed`.
- `add_path` with a complete validated node list, or `delete_path`.

Only line, cubic and quadratic segments are supported. Locked, malformed,
degenerate, non-finite, oversized, unknown-type or hint-referenced targets are
rejected. No hint is silently removed. Limits are 256 operations, 4,096
expanded layer changes and 4,096 nodes per path.

Review the complete report, especially per-layer inserted coordinates, raw-node
deltas, native removals, adjusted surviving nodes, compatibility diagnostics
and warnings. A zero raw-node delta can still include a split followed by a
native removal; inspect the operation evidence. Applying does not Save. It
retains native per-glyph Undo/Redo, partial-write recovery, whole-job
`discard_job`, path metadata, components, anchors, surviving node identities
and shape order. Apply only from the same saved clean baseline.
