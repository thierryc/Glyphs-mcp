# Create a new font

Require `create_document` in the specific connection's catalog and
`document.create.v1` in `get_status.writeCapabilities`. Earlier twelve-tool
installations need a coordinated bridge/sidecar/skills update for this operation.

Under the user's creation request, call `create_document` with `family_name`, a
fresh retained `idempotency_key` and optional integer `units_per_em` (16–16384,
default 1000). Family name and key must be 1–255 characters without control
characters. This opens an unsaved font with one Regular master, one Regular
instance, native default axes/metrics and no initial glyphs. No document discovery,
saved baseline, script, preview or additional Run question is needed for creation.

Retain the returned `id` as this connection's document binding; `masterIds` and
`instanceIds` are native identities for subsequent operations. Reads need no Save.
The existing edit-job baseline rules continue to apply. When the task already
authorizes saving, use `save_document` with that ID and an absolute new `.glyphs`
or `.glyphspackage` destination. Creation alone does not authorize saving.

After a timeout, retry the same key and arguments. Never submit a new key just
to recover an uncertain creation. `creation_conflict` means the key's arguments
differ; `document_not_found` means the created font closed and is not recreated.
After a bridge restart, `creation_outcome_unknown` requires fresh discovery and
explicit resolution of the original font. `creation_failed` may include an owned
`documentId` for a partially opened font; report it and inspect, without repeating
creation or closing it implicitly. No MCP job rollback applies to document creation.
