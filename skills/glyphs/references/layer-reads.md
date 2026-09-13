# Native layer measurements

Reuse the catalog and `get_status` evidence from the specific connection. Require
`layer.read.exact.v1` in the negotiated `readCapabilities`. If missing, explain
that the private installation needs updating: update the bridge, sidecar and
skills together and verify fresh status. Do not substitute older lookup behavior
or accept unverified identity. Layer reads require a nonempty exact native layer
ID and return `id` from native `layerId`.

Reuse the retained document ID; call `list_documents` only if it needs resolving,
following [document targeting](document-targeting.md). Reuse known ordinary master
IDs; otherwise discover them using the [master reference](master-reads.md). Their ordinary layers use those
IDs. Special/backup layers need their own exact layer IDs. This interface does
not enumerate special layers or infer them from names.

Call `read_entities` with 1–100 explicit entities and 1–32 supported fields:

```json
{
  "document_id": "<resolved document ID>",
  "entities": [{"kind": "layer", "glyph": "A", "id": "<native layer ID>"}],
  "fields": ["id", "name", "width", "vertWidth", "vertOrigin",
             "leftMetricsKey", "rightMetricsKey", "widthMetricsKey", "bounds"]
}
```

Those fields plus `outlineHash` are the complete supported layer field set.
IDs are opaque strings, not necessarily UUIDs. The glyph name and layer ID
must be nonempty strings; omission or wrong types return `invalid_request`.
A missing glyph/layer or a name alias returns `target_not_found`. A name that
happens to equal a genuine native ID is interpreted only as that exact ID.
A missing target rejects the entire mixed request; there is no partial pass.
Unsupported fields return `unsupported_read`; do not substitute zero for null.

Dirty and unsaved documents remain readable without saving. These are live
reads, not a saved-source snapshot. Re-resolve after closing/reopening a font;
do not reuse a previous document ID or claim atomicity across multiple calls.

`width` is the horizontal advance. `vertWidth` and `vertOrigin` report stored
native optional values: null means unset/unavailable, while numeric zero is a
value. They do not resolve inherited vertical metrics. Layer metrics keys are
stored overrides, separate from glyph-level keys and effective synchronized
values. This interface does not expose glyph-level keys, master ascender/
descender, or resolved metric inheritance. Do not call `syncMetrics()` while
claiming to perform a read-only inspection.

For a confirmed nonempty outline with bounds `(x, y, w, h)`, physical fractional
horizontal bearings are `LSB = x` and `RSB = width - x - w`. Negative bearings
are valid measurements. Native displayed bearings may be rounded. Use native
bounds for cubic extrema and transformed components; control-point bounds are
not the same. Zero-area bounds alone cannot distinguish empty outlines from
degenerate shapes, so do not assert an empty layer's bearings from that formula.

`outlineHash` is an opaque change guard, not interpretable geometry. Detailed
nodes, component references and shape counts are unavailable through these
layer fields. For selected node evidence in the active Edit View, use the
[selection reference](selection-reads.md) with `selection.context.v1`. Native UI/companion inspection or a separately authorized workspace
script can supply additional evidence; label that route and its limits. Never
silently fill missing public results from an independent verification helper.

Report selected document/layers, exact returned values, derived quantities and
unavailable evidence separately. A measurement request needs no job, preview,
application, Save or Undo. Do not equate accurate values with good spacing or
interpolation.
