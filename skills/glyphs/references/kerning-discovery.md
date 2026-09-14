# Discover native kerning groups and stored pairs

Reuse the verified connection, known document ID and exact master IDs. Require
`kerning.groups.v1` for group/key fields and `kerning.pairs.v1` for pair pages in
negotiated `get_status.readCapabilities`. If absent, update bridge, sidecar and
skills together. No earlier-private fallback. Reads work on dirty/unsaved fonts
without Save or a job. Known pairs still use [exact reads](kerning-reads.md).

## Group names and lookup keys

For named glyphs (up to 100), request only needed native properties:

```json
{"document_id":"doc_…","entities":[{"kind":"glyph","id":"A"}],"fields":["leftKerningGroup","rightKerningGroup","leftKerningKey","rightKerningKey"]}
```

Also available: `topKerningGroup`, `bottomKerningGroup`, `topKerningKey`,
`bottomKerningKey`. Group properties are unprefixed names or native null. Key
properties return native prefixed group keys, or the glyph name when ungrouped.
Do not invent group assignments from names. In LTR, the first glyph uses
`rightKerningKey` (`@MMK_L_…`), the second uses `leftKerningKey` (`@MMK_R_…`).
Top keys use `@MMK_B_…`, bottom keys `@MMK_T_…`. Keep the explicit direction and
raw table order: do not reinterpret RTL/vertical pairs through LTR precedence.
These properties are lookup inputs; glyph names are not native raw storage IDs.

## Stored-pair pages

```json
{"document_id":"doc_…","entities":[{"kind":"kerning_pairs","master":"exact-master-id","direction":"LTR","limit":100}],"fields":["left","right","value"]}
```

One selector only; explicit direction is `LTR`, `RTL` or `vertical`. Choose any
nonempty subset of `left`, `right`, `value`. Each requested side contains
`key` (exact raw stored key), `glyph` (resolved name or null), and `kind`
(`group`, `glyph`, or `unresolved`). Native glyph IDs are resolved individually;
an unresolved key is evidence of storage, never a guessed glyph. For existing
exact-value reads use `key` for groups, `glyph` for resolved glyphs; unresolved
keys cannot be passed as glyph names.

`values` contains `items`, `returned`, `total: null`, `complete`, `nextCursor`,
`scanned` and `scanLimit: 256`. The total is unavailable: counting it would walk
the whole table. `complete: true` means this traversal reached its end, not that
this page contains all pairs. Preserve zero and fractions; missing stored pairs
are omitted, not represented as zero. This is storage, not effective kerning.

Optional `leftKey` and/or `rightKey` are single exact **raw keys** copied from
storage (maximum 1024 characters). A left filter looks up one native group;
a right filter looks up that key within each outer group. Unknown raw filters
produce no matches. Do not pass a glyph name as a native storage ID.

Limit 1–100, default 100. Each page also stops after 256 work units, charging
outer groups (even empty groups/filter misses) and inner entries. Thus a page
may be empty and incomplete. Always follow `nextCursor` unchanged with the same
master, direction and filters until complete; never infer completion from item
count. Later pages resume native indices without rescanning previous groups.
There is no sorting, font-wide ID map or cached table.

Pages are live, not atomic. `stale_kerning_cursor` or an observed edit means
**discard partial results and restart without a cursor**. Existing generation,
dirty, outer-count and last-boundary guards reject observed changes; silent
same-count changes away from the boundary or reverted edits can escape them.
Dirty redraws can conservatively invalidate a cursor. Keep the known document
ID unless `document_not_found` requires discovery. No automatic font substitution.
Missing master is `target_not_found`; invalid direction/limit/filter/cursor is
`invalid_request`; unavailable native indexed evidence is `unsupported_read`.
No kerning/group writes, collision jobs or native scripts are needed to inspect.
