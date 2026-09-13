# Identify native masters

Use this connection's verified `get_status` evidence and retained document ID;
do not repeat either setup call for this reference. If the binding is absent,
resolve it once with `list_documents`. Follow
[document targeting](document-targeting.md) for stale IDs or a changed target. For live discovery, require `masters.list.v1` in
the negotiated `readCapabilities`. The seven tools and protocol 1 alone do not prove
this newer read is available. A stopped bridge provides no verified capability.

Enumerate masters when their IDs are unknown or a current inventory is requested;
known exact IDs need no preliminary master list. Call
`read_entities(document_id=..., entities=[{"kind":"masters","limit":100}],
fields=["id","name"])`. This reads Glyphs' native master collection in order,
including dirty and unsaved fonts, without a source script or Save. The one result's
`values.items` contains IDs/names; `values.total` is the current native count.
`values.complete: false` means the evidence is incomplete. Pass `values.nextCursor`
unchanged as `cursor` in the next otherwise identical selector until complete.
An empty font returns an empty complete page. Do not guess IDs from names.

A page must be the only selector. Its limit is an integer 1–100 (default 100);
fields are `id` and/or `name`. Page size does not raise the existing 100-target
bound. Do not mix a page with glyphs, layers or explicit masters. Reject partial
coverage as a complete inventory; report examined/total counts if stopping early.

After discovery, use exact selectors for a known subset:
`entities=[{"kind":"master","id":"<native ID>"}], fields=["id","name"]`.
`master.read.exact.v1` advertises strict lookup. IDs are opaque strings, not
necessarily UUIDs. Names can be duplicated. Missing/empty IDs return
`invalid_request`; a name substituted for an ID or an unknown ID returns
`target_not_found`. One missing target rejects the entire mixed request;
retry only a verified valid subset and report the omission.

`stale_master_cursor` means the document, master count or preceding page boundary
changed. Discard the partial inventory and restart without a cursor. Pages are
live reads, not an atomic multi-call snapshot: arbitrary edits between calls
are not all detectable. Keep editing paused during collection; after an observed
edit, re-enumerate. Re-resolve a document after closure/reopening. This does not
claim to fix document-ID lifetime behavior.

Require `masters.list.v1` for discovery and `master.read.exact.v1` for exact
master reads in this private installation. If a required capability is missing,
explain that the installation needs updating: update the bridge, sidecar and
skills together, then verify fresh status. Do not substitute earlier private
lookup behavior, a saved-source script or Font Info as a fallback workflow.
Dirty and unsaved inspection needs no Save, job, master creation or live Python.
