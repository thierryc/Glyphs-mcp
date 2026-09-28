# Glyph color tags

Use this for requests such as “mark A, B and C orange for review” or “clear the
color on these named glyphs.” Color tags are Glyphs UI metadata, not outline or
COLR artwork. Require an explicit intended `document_id` and glyph names; do not
infer targets from selection, another font, or a failed lookup.

Read existing tags first with `read_entities(document_id, entities=[{"kind":"glyph","id":"A"}], fields=["name","color"])`.
Repeat for the explicit glyph list, up to 100 per call. `color` is the native
Glyphs palette index; `null` means no standard palette index. A custom color
label may also read as `null`. The action refuses custom labels it cannot
restore from an index; inspect those glyphs in Glyphs. The closed palette is red=0,
orange=1, brown=2, yellow=3, light_green=4, dark_green=5, light_blue=6,
dark_blue=7, purple=8, magenta=9, light_gray=10, charcoal=11. Use `none`
to clear a tag. Do not confuse `none` with red=0.

For a requested change, require `native_action` in `get_status.jobKinds`,
`native.action.v1` in `writeCapabilities`, and `set_glyph_color` in
`nativeActions`. The action uses the existing guarded job workflow; there is no
arbitrary glyph-property write tool. For example, prepare a preview for orange:

```json
{
  "document_id": "<intended document ID>",
  "kind": "native_action",
  "options": {
    "action": "set_glyph_color",
    "arguments": {"color": "orange"},
    "targets": [{"glyph": "A"}, {"glyph": "B"}]
  }
}
```

Use `start_edit_workflow` with these `document_id`, `kind`, and `options`, a
stable `idempotency_key`, and `mode="preview"` when the user asks to preview.
For an authorized edit, use `mode="apply"`; inspect the complete report if it
requires review. `start_job`, `get_job`, and `apply_job` are the lower-level
equivalent. The report lists each target's old and new `color` index, including
no-op targets. Re-read the named glyphs after application to confirm the tags.
Native Undo/Redo and `discard_job` remain available. Do not call `accept_job`
or `save_document` merely to apply colors: application stays unsaved. A job
requires a saved, clean source for preparation; if the font is dirty or new,
the [conversation workflow](edit-workflow.md) offers explicit save choices.
Explain that a prerequisite save persists the whole existing font, while the
subsequent color change still remains unsaved.

On a supporting bridge, color preparation copies only glyph metadata, leaving
outlines and backgrounds untouched. The report and metadata conflict guards are
unchanged. Custom labels are checked before the metadata copy, because Glyphs
does not preserve custom color objects in that copy. Application and selective
recovery still use the existing persisted-state guards; preparation speed does
not imply the same improvement for the whole edit. The 100-glyph action bound
is unchanged.
