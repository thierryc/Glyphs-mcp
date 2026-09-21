# Closed native actions

Use `native_action` only when `get_status.jobKinds` contains `native_action`,
`writeCapabilities` contains `native.action.v1`, and the requested action is in
the same response's sorted `nativeActions` array. The list is negotiated with
the exact running Glyphs build. A missing action is unavailable; do not replace
it with a script, menu invocation, guessed selector or arbitrary Python.

Native actions use the existing nine-tool job lifecycle. They require a saved,
clean source. Call `start_job`, poll `get_job`, read the full report and its
before/after summaries, then call `apply_job` only after review. Application is
save-free and registers native Undo/Redo. `discard_job` restores the entire
unaccepted job. When the user's task authorizes persistence, `accept_job`
revalidates the native hashes, saves the whole document and returns its receipt.

## Request shapes

Each job performs exactly one action. Layer actions use 1–100 glyph targets:

```json
{
  "document_id": "<document ID>",
  "kind": "native_action",
  "options": {
    "action": "update_metrics",
    "targets": [{
      "glyph": "h",
      "layers": {"scope": "all_masters"}
    }]
  }
}
```

Replace the layer scope with `{"scope":"ids","ids":["<exact layer ID>"]}`
to target stored special layers. `all_masters` addresses ordinary master layers
only; it excludes brace, bracket, other special and background layers. Exact
IDs come from layer discovery and may not be names or arbitrary selectors.

`update_glyph_info` uses `targets:[{"glyph":"A"}]`. `update_features` is
font-scoped and forbids `targets`. `update_automatic_feature_block` uses exact
targets such as `{"blockType":"feature","id":"<persistent ID>"}` and is
restricted to native blocks that report both `automatic` and `canBeAutomated`.
Only `add_extremes` accepts arguments:
`"arguments":{"force":true}`; `force` defaults to `false`. Do not send top-level
`delta` or `glyphs`, action-specific unknown fields, selector names or menu names.

## Catalog and risks

| Action | Scope | Fixed native behavior | Review focus |
|---|---|---|---|
| `update_metrics` | layer | Apply metrics keys with `syncMetrics()` | Keys and resulting bearings/width; this is not bearing recalculation. |
| `correct_path_direction` | layer | Correct contour direction | Counters, overlaps and winding. |
| `round_coordinates` | layer | Round native coordinates | Fractional geometry and compatibility. |
| `add_extremes` | layer | Add extrema without selection dependence | New nodes and compatibility; inspect `force`. |
| `cleanup_paths` | layer | Native path cleanup | Removed/changed nodes and handles. |
| `remove_overlap` | layer | Remove all overlap, never selection-only | Contour topology and appearance. |
| `add_missing_anchors` | layer | Add Glyphs-derived anchors | Anchor names and positions. |
| `align_components` | layer | Immediate native component alignment | Component positions and automatic alignment. |
| `decompose_components` | layer | Decompose components | Resulting contours and source references. |
| `decompose_corners` | layer | Decompose corner components | Corner geometry and compatibility. |
| `make_components` | layer | Convert eligible outlines to components | Component choice and geometry. |
| `reinterpolate` | layer | Native reinterpolation | Master correspondence and intended interpolation source. |
| `connect_open_paths` | layer | Connect all eligible open paths | Endpoint pairing and contour order. |
| `swap_foreground_background` | layer | Swap the complete foreground/background pair | Both sides of the swap; background is retained for restoration. |
| `update_glyph_info` | glyph | Update metadata with renaming disabled | Unicode/category/script/production metadata; names must not change. |
| `update_features` | font | Update automatic prefixes, classes and features | Generated source and compiler diagnostics. |
| `update_automatic_feature_block` | feature block | Call native `update()` on one exact automatic, automatable prefix/class/feature | Generated source, block identity and diagnostics. |

Compile-only work uses the separate closed `feature_compile` diagnostic job;
verified binary generation uses `font_export`. Generic menu execution, arbitrary
selectors, renaming and selection-sensitive variants are outside this contract. The
report distinguishes changed and no-op targets, includes warnings and links to
the full report. A no-op is evidence that the fixed native call produced no
persisted change on that target, not that another action should be substituted.

The contract bounds requests to 100 explicit targets and 4,096 expanded layers.
Each canonical persisted target state is limited to 8 MiB and the job to 64 MiB.
Hash conflicts, readback failures or mid-batch exceptions trigger exact native
snapshot restoration and rollback; report incomplete recovery rather than
claiming a clean result.
