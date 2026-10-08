# Open an existing font

Require `open_document` in this connection's tool catalog and `document.open.v1`
in `get_status.writeCapabilities`. Older bridges need a coordinated update;
do not route a missing advertised capability through an edit script.

Under the user's file-opening request, call `open_document` with an absolute local
`path` and a fresh retained `idempotency_key`. Native `.glyphs` files and
`.glyphspackage` directories are supported; URLs, missing sources and binary/UFO
imports are not. File aliases are resolved to their canonical path.

No existing document, saved baseline, prerequisite Save or edit job is required.
An already-open source is reused without reloading or changing its unsaved edits.
Opening never saves, closes another font or changes its contents. A reused font
is not explicitly brought to the front; `alreadyOpen` distinguishes that result.
If multiple live documents match the source, `ambiguous_document` returns their
IDs without choosing a font or opening another. Resolve the intended document
from fresh discovery before further work.

Retain the returned `id` as the document binding for reads and edits. The result
also includes `path`, `familyName`, `dirty`, `generation`, `alreadyOpen`, `openId`
and `bridgeSessionId`. Opening does not authorize subsequent edits or saving.

After a timeout, retry the same key and path; never use a new key to bypass an
uncertain result. The sidecar journals the request before dispatch and the bridge
retains its outcome. `opening_conflict` means the key belongs to another path.
If the opened font has since closed, retry returns `document_not_found` and does
not reopen it. A new user request to reopen it uses a fresh key.

After a bridge restart or unreadable journal, `opening_outcome_unknown` requires
fresh document discovery and reconciliation of the exact source. A partial native
failure can include `documentId` in error details: inspect that document without
repeating Open or closing it implicitly. No edit-job rollback applies to opening.
