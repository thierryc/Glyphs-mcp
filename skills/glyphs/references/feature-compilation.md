# OpenType feature discovery and compilation

Reuse the verified connection and intended document ID. Compilation is a
closed diagnostic job, not a mutation or arbitrary compiler API. Require
`feature_compile` in `get_status.jobKinds`, then choose only a mode advertised
in the same response's `jobCapabilities`.

## Discover exact source blocks

Require `features.read.v1`. Discover one native collection at a time with
`{"kind":"feature_blocks","blockType":"feature","limit":100}` and
`fields:["items"]`; `blockType` is `prefix`, `class` or `feature`. Follow the
opaque `nextCursor` until `complete:true`. Restart without the cursor after
`stale_feature_cursor` or an observed edit. Pages are live, not atomic.

Read an exact block with
`{"kind":"feature_block","blockType":"feature","id":"<persistent ID>"}`.
Request only needed fields from `id`, `name`, `code`, `automatic`, `disabled`,
`canBeAutomated`, `notes`, `labels`, `errors`, `errorType`, `errorTooltip` and
`filePath`. Names are not IDs. Dirty documents are readable without saving.

For one automatic block, use the separately advertised
`update_automatic_feature_block` native action only when both `automatic` and
`canBeAutomated` are true. For all automatic source, use `update_features`.
Review generated source before acceptance; neither action is a compile-only
operation.

## Compile without changing source

Saved-source compilation is the default:

```json
{"document_id":"<document ID>","kind":"feature_compile","options":{"mode":"saved"}}
```

Require `feature.compile.saved.v1`. The external Glyphs worker opens the exact
saved snapshot, calls `GSFont.compileFeatures()`, checks its explicit
success/error result, verifies the complete persisted feature state did not
change and never saves the font.

Use `"mode":"live"` only with `feature.compile.live.v1`. It calls the same
native compiler on the clean open document on Glyphs' main thread, retains and
verifies the persisted feature-state hash, and reports its compiler state as
ephemeral. Both modes currently require the common saved, clean job baseline;
live mode is for exact running-build diagnostics, not unsaved-source access.

Poll `get_job` until terminal `completed`. A compiler rejection is a successful
diagnostic run with `report.success:false` and normalized errors; it is not a
worker failure. Read block IDs/names and native messages from the report. Do not call `apply_job`,
`accept_job` or `discard_job` for a terminal diagnostic job.

Compilation proves only that the tested source is accepted by that Glyphs build.
It does not prove exported behavior, script/language coverage or feature-on/off
shaping. Use verified export when the task requires binary behavior evidence.
Never substitute a script, selector or menu command when the capability is not
advertised; update the coordinated bridge, sidecar and skills installation.
