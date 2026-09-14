# Discover one glyph's layers

Reuse this connection's retained document ID and status. Require negotiated
`layers.list.v1`; if absent, explain **“This installation needs updating: update
the bridge, sidecar and skills together to use layers.list.v1.”** No earlier-private
request, script or UI fallback. Known exact layer IDs need no inventory; use the
[layer measurements](layer-reads.md) request directly.

For unknown IDs, use one named glyph per page, requesting only needed fields:

```json
{"document_id":"doc_…","entities":[{"kind":"layers","glyph":"a","limit":100}],"fields":["id","name","associatedMasterId","isMasterLayer","isSpecialLayer","isBraceLayer","isBracketLayer"]}
```

`values` contains `items`, `total`, `returned`, `complete` and `nextCursor`.
The integer limit is **1–100**, default 100. No mixed selectors or geometry fields.
Items contain only requested fields. IDs are exact native `layerId` strings;
duplicate names are valid and never identify a target. An item can be read next
with `{"kind":"layer","glyph":"a","id":"<returned id>"}` and fields such as
`["id","width","bounds"]`. A round trip needs no document rediscovery.

Order is **native collection order** (`objectInLayersAtIndex_`), not a new sort,
the Layers panel's presentation or the Python wrapper's master-first order.
This inventories that glyph's stored layer collection, including ordinary,
special and backup/extra layers. Nested backgrounds are not separate entries;
do not call this an inventory of background objects or all font glyphs.

Native classification evidence is independent: `isMasterLayer`, `isSpecialLayer`,
`isBraceLayer` (intermediate), `isBracketLayer` (alternate). A non-master with all
special flags false is an ordinary extra/backup candidate, not proof of its
purpose. Other special layers may have neither brace nor bracket set. Report
overlapping or ambiguous flags as returned; do not infer grouping rules or
compatibility from names, associated masters or these flags. `associatedMasterId`
is the native association, not permission to treat a special layer as a master.
Unknown/unavailable optional metadata returns null, never a fabricated false or
empty string. Inventory completeness does not certify classification certainty.

On `complete:false`, pass `nextCursor` unchanged in the next selector for the same
glyph and document. Check aggregate returned count against total. If stopping
early, report “N of total layers read”. Empty collections are explicitly complete
with zero items; unavailable native count/index/identity produces an error.

**Pages are live, not atomic.** On `stale_layer_cursor` or any observed edit,
discard partial results and restart without a cursor. Guards bind document/glyph,
count, existing generation/dirty signals and the preceding layer ID/name. They
cannot detect every silent same-count edit or reverted change away from the
boundary. Dirty-document redraw/selection can conservatively invalidate pages.
Use a quiet read interval if interrupted; do not merge partial inventories or
retry indefinitely. Remembering an ID never caches that layer's contents.

`target_not_found` means a missing glyph/layer: correct the target, retaining the
document ID. Only `document_not_found` or changed document intent requires
[fresh targeting](document-targeting.md). No Save, job, edit, preparation or Undo
is needed. Dirty and untitled documents remain readable.
