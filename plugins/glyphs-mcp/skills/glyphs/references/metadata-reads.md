# Bounded glyph metadata reads

Reuse the specific connection already identified by `$glyphs` as the seven-tool
lean sidecar and its retained document ID. Only if that binding is missing, use
`list_documents` to resolve the intended path; follow
[document targeting](document-targeting.md). Dirty documents remain readable without saving.

Call `read_entities` with 1–100 explicit entities and 1–32 supported fields.
For glyph metadata, use `{"kind":"glyph","id":"A"}`. Available fields are
`name`, `unicode`, `category`, `subCategory`, and `export`.

```json
{
  "document_id": "<ID returned by list_documents>",
  "entities": [{"kind":"glyph","id":"A"},{"kind":"glyph","id":"a"}],
  "fields": ["name","unicode","category","subCategory","export"]
}
```

Split larger explicit scopes into batches of at most 100; retain each batch's
requested and returned names. Empty and over-100 requests are invalid. These
reads do not enumerate all glyphs. Preserve `null` and `false` values in reports.

**A missing glyph rejects the entire request** with `target_not_found`; no
partial results are returned. For example, if `["A","a","missing.name"]`
fails and names `missing.name`, record that missing target and retry the explicit
known subset `["A","a"]` using the same selector shape above. Do not report the
original scope as complete or silently drop failures. Keep the same document ID
for this missing-glyph recovery. Rediscover only after `document_not_found` or
a changed target; an unavailable document is a different error.

**`unicode` is the primary mapping.** A native glyph with mappings `E102` and
`E103` returns `E102` here. The complete `unicodes` list is unavailable through
this build's projection; requesting it returns `unsupported_read`. Do not infer
that secondary mappings are absent or claim a complete Unicode audit. Use an
explicitly requested native Glyphs inspection for that separate task.
