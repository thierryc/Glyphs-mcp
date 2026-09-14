# Discover glyph names

Use this connection’s retained document ID and verified status. Require negotiated
`glyphs.list.v1`; if missing, explain **“This installation needs updating: update
the bridge, sidecar and skills together to use glyphs.list.v1.”** Do not substitute
older private requests or a script/UI fallback. Known glyph names need no inventory;
use the existing explicit `{"kind":"glyph","id":"A"}` selector directly.

To discover names, request one page only:

```json
{"document_id":"doc_…","entities":[{"kind":"glyphs","limit":100}],"fields":["name"]}
```

Example `values`:

```json
{"items":[{"name":"A"},{"name":"V"}],"total":2,"returned":2,"complete":true,"nextCursor":null}
```

`limit` is an integer **1–100**, default 100. Initially `name` is the only page
field. Do not mix a glyph page with other selectors. Native glyph collection
order is preserved; it is not a separately sorted inventory or Font View filter.
No outlines, geometry or other metadata are loaded by this projection.

If `complete:false`, retain these items and pass `nextCursor` unchanged in the
next selector: `{"kind":"glyphs","limit":100,"cursor":"<returned opaque string>"}`.
Do not decode, manufacture, edit or reuse a cursor with another document. Only
`returned` items have been examined on that page. Continue until complete and
check the aggregate count against total before reporting full coverage. If
stopping early, report “N of total names read”. An empty font returns total and
returned zero, empty items, complete true and nextCursor null. Missing native
count/name/index evidence is an explicit error, never a complete empty inventory.

**Pages are live, not atomic.** `complete:true` means the last index was reached
with the checks below passing; it does not certify a snapshot across calls.
Keep edits paused during enumeration. After **any observed edit**, discard the
partial inventory and restart without a cursor. Re-read named targets when their
current properties are needed; remembering an inventory does not cache contents.

`stale_glyph_cursor` detects changed document binding, count, existing document
change signal, dirty state, or the preceding boundary glyph’s native ID/name.
Discard partial results and restart. The existing dirty-document update signal
is conservative: selection/redraw activity can also invalidate a cursor. These
bounded guards cannot detect every silent, same-count change elsewhere in the
font or an edit that was reverted between calls. Do not claim that they can.
If changes keep interrupting collection, explain the interruption and obtain a
quiet read interval rather than retrying indefinitely or merging inconsistent pages.

`document_not_found` uses [document targeting](document-targeting.md): rediscover
and resolve the intended font explicitly, then start a new inventory. Other
invalid limits/fields need a corrected request, not document rediscovery.
Dirty and untitled fonts need no Save, preparation, job or new Undo operation.
