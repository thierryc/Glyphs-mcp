# Current master and selected glyphs

For document context, check the retained status of this **specific MCP connection**
for negotiated `document.context.v1`. If missing, explain **“This installation needs
updating: update the bridge, sidecar and skills together to use document.context.v1.”**
Do not substitute an earlier private request, script or UI fallback. The older
`selection.context.v1` flag covers node/object selection, not this projection.

Reuse the intended document's retained ID; [targeting](document-targeting.md)
explains explicit current-font intent and stale IDs. Context never changes the
font target when another window becomes current. Request only needed fields:

```json
{"document_id":"doc_…","entities":[{"kind":"context"}],"fields":["view","master","selectedGlyphs"]}
```

Example `values` (the tool retains its existing response envelope):

```json
{"view":"font","master":{"id":"native-master-id","name":"Regular"},"selectedGlyphs":{"source":"font.selection","total":2,"returned":2,"limit":100,"complete":true,"items":["control","mixed"]}}
```

- `view`: `font`, `edit` or `unavailable`. Native selected-tab identity establishes
  the view; absence of an Edit View alone does not prove Font View.
- `master`: the native toolbar-selected master’s exact `id` and `name`, or null
  when that evidence is unavailable. It does not identify a special layer.
- `selectedGlyphs`: native-order glyph names from **font.selection** in Font View
  or **font.selectedLayers** parents in Edit View. The bridge does not sort or
  deduplicate. In Glyphs 4.1 (4107), selecting repeated occurrences of the same
  layer in Edit View yields that layer once; a text caret can yield its active
  layer. These are native selection entries, not a count of text occurrences,
  selected nodes, or every glyph displayed in the tab. Names can repeat when
  distinct native selected layers refer to the same glyph.

`total` is the native collection count, `returned` counts included names, and
`complete` says whether every entry is represented. Native empty selection has
zero total/returned, empty items and complete true. Missing evidence has
complete false, an `unavailable` reason and a null total when the count is unknown;
it must never be described as an empty selection. Partial item evidence retains
its prefix and native total with complete false.

Default and maximum **100** names. Optional `glyphLimit` is an integer 1–100,
allowed only when requesting `selectedGlyphs`:
`{"kind":"context","glyphLimit":10}`. Use one context entity only. No cursor,
pagination, implicit reselection or font traversal. Say “10 of 120 native selection
entries returned” when complete:false. Narrow the selection or obtain an explicit
complete target list before any edit based on incomplete evidence.

This compact read includes no nodes, outlines or extra glyph metadata. Use
[selection reads](selection-reads.md) separately for active-layer object counts
or optional node details (default 64, maximum 256). Context reads are fresh on dirty
and unsaved fonts and need no Save, job or Undo operation.
