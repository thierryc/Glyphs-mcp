# Verified static, variable and web-font export

Export is one closed `font_export` job over one exact native instance. It runs
in the external Glyphs worker against the saved clean snapshot, never saves the
source, and stages output privately until explicit publication. Require
`font_export` in `jobKinds`, `instances.read.v1`, `font.verify.tables.v1`, and
the matching capability in `jobCapabilities`.

## Select an exact instance

Discover with `{"kind":"instances","limit":100}` and `fields:["items"]`.
Follow the opaque cursor to `complete:true`; restart on `stale_instance_cursor`.
Summaries include persistent `id`, name, static/variable type, export flag and
outline format. Read exact details with `{"kind":"instance","id":"<ID>"}`
and needed fields from `id`, `name`, `type`, `exports`, `outlineFormat` and
`axisValues`. Do not use a display name as `instanceId`; disabled instances are
rejected.

Require `font.export.static.v1` or `font.export.variable.v1` for that instance.
WOFF or WOFF2 additionally requires `font.export.web.v1`. Requested shaping
cases require `font.verify.shaping.v1`.

```json
{
  "document_id":"<document ID>",
  "kind":"font_export",
  "options":{
    "instanceId":"<persistent instance ID>",
    "format":"otf",
    "containers":["plain","woff2"],
    "generation":{
      "autoHint":true,
      "useSubroutines":true,
      "useProductionNames":true,
      "decomposeSmartComponents":true
    },
    "verification":{"shapingCases":[{
      "text":"ffi","feature":"liga","expect":"different",
      "controlText":"abc","script":"latn","language":"dflt",
      "direction":"ltr"
    }]}
  }
}
```

`format` is `otf` or `ttf`; containers are 1–3 unique values from `plain`,
`woff` and `woff2`. Typed generation defaults are `autoHint:true`,
`useProductionNames:true`, `decomposeSmartComponents:true`, and OTF
`useSubroutines:true`. Static export defaults `removeOverlap` to true. Variable
export fixes it to false and rejects true. TTF rejects subroutines.

At most 32 shaping cases are accepted. Each uses a four-character feature tag,
explicit `same`/`different` expectation, optional unaffected `controlText`,
direction/script/language, value and finite variation coordinates. These are
bounded samples, not exhaustive proof.

## Review and publish

Poll to `ready`, then inspect `resultKind:"artifact"`, report and manifest.
Glyphs generation is accepted only when fontTools parses every file, required
tables and requested outline/container/variable structures match, and every
requested HarfBuzz case passes. The manifest contains exact relative paths,
sizes and SHA-256 hashes. It allows 1–3 regular files, at most 512 MiB each and
1 GiB total; symbolic links and special files are rejected.

Do not call `apply_job`: artifacts do not mutate the open document. Call
`discard_job` to delete private staging, or, when publication is authorized,
call `accept_job` with a new absolute destination directory. The destination
and every parent must be real paths and the destination must not exist. The
sidecar rechecks the clean source and staged hashes, copies into a private
sibling, fsyncs it, and publishes by atomic rename without overwrite. Its
receipt binds the source hash, manifest and destination. Interrupted publication
is reconciled from exact destination hashes and is never replayed blindly.

Export evidence covers only the requested instance, containers, structural
checks and explicit shaping samples. It does not establish a full font audit.
Missing capability is unavailable; do not replace it with arbitrary Python.
