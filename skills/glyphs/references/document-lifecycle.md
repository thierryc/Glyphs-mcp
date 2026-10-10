# Import, activate, open Edit tabs and close fonts

Require the tool and its matching `document.import.v1`, `document.activate.v1`
`document.edit-tab.open.v1` or `document.close.v1` write capability on this connection. Missing capabilities
need a coordinated bridge/sidecar update, not an edit-script fallback.

Under file-import authorization, call `import_document(path, idempotency_key)`
with an absolute local `.ufo` folder, `.otf` file or `.ttf` file. No existing
font, script or saved baseline is needed. Retain the returned `id`; a compiled
import can be pathless and is view-only until native Save As. Explain reported
hinting/OpenType-table losses when relevant. Import never saves, exports or
overwrites the source, and does not change Glyphs import preferences. Use
`save_document` only under save authorization, with a new `.glyphs` or
`.glyphspackage` destination. Saved native sources can then become job baselines.

Retry the same import key and path after a lost response. `importing_conflict`
means different arguments; `document_not_found` means the returned font closed,
without reopening it. `importing_outcome_unknown` after a bridge restart or
unreadable journal requires reconciling the original import before a new request.
An attempted native failure is retained and never implicitly replayed.

Use `activate_document(document_id)` for a requested font/window switch. Resolve
the exact live document ID using the retained binding or fresh discovery when
needed. It shows that window and requests Glyphs activation; `isCurrent` reports
the observation. Repeated activation is safe and does not reopen closed fonts,
change outlines, save or resolve jobs.

## Duplicate the current font without saving

Call `duplicate_document(document_id, idempotency_key, family_name=None)` under
`document.duplicate.v1`. Copy the exact live font, including unsaved edits, into
an independent pathless document; optionally rename only its family. The source
is unchanged and neither document is saved. Use the returned `id` for demo edits,
proof tabs and separately authorized Save As.

Retain one key per copy. Identical retries reuse the original result; changed
arguments conflict, closed copies are not recreated, and bridge restarts or
partial native failures require reconciliation. Pending jobs owning the source
must be resolved before duplication. Do not use the current font implicitly.

## Open an Edit tab without saving

For a requested Edit tab or proof display, call
`open_edit_tab(document_id, idempotency_key, text=None, glyphs=None, master_id=None)`
under `document.edit-tab.open.v1`. Dirty and pathless fonts are supported without
Save, scripts or an edit workflow. Use the exact live font binding; activation
alone does not open an Edit tab.

Supply Unicode proof `text` (maximum 4096 characters, native `/glyphName` syntax),
or 1–100 exact `glyphs` in display order, preserving repeats. Omit both for a
blank tab. Never supply both. An optional exact `master_id` selects its master;
otherwise the font's current master is retained. Missing glyph/master layers
reject before opening. Existing tabs and geometry are preserved; no save occurs.
Native UI state may affect Glyphs' dirty flag; never reset it to disguise a change.

Keep one fresh key per intended tab and retry the same arguments after lost
responses. Different arguments return `edit_tab_conflict`. `edit_tab_closed`
never recreates the original tab. `edit_tab_outcome_unknown` requires inspecting
and reconciling the original result, including after bridge restarts; never retry
with a new key blindly. IDs for tabs are session-local and are receipts only;
listing, editing, closing tabs and special-layer targeting are not exposed.
Pending owning jobs block this UI-context change; resolve their existing lifecycle.

Close only when the user's task authorizes closing that font. Use
`close_document(document_id, idempotency_key, unsaved_changes="refuse")` by
default. Unsaved or unknown changes give `unsaved_changes_required`: offer Save,
Discard or Cancel in ordinary language. Reuse save authorization already given.
`save` verifies the native save and source hash before closing; pathless/imported
fonts require a new native `destination`. Save/checkpoint failure leaves the
font open. `discard` requires explicit authorization to lose **all unsaved edits
in this font**, including manual changes. Cancel means no tool call.

Pending, ready, applied, active and uncertain jobs block Close. Resolve their
existing lifecycle before retrying; Close is not a replacement for Keep, Save,
Discard or saved-version recovery. Never close another font to clear an error.

Retain the same Close key, document ID, choice and destination after lost responses.
The original result remains available after closing, without another native
Close or Save. `closing_conflict` means options changed; `stale_document` means
the font changed after the choice was prepared. Review the new state before a
new intent. `closing_outcome_unknown` requires outcome reconciliation, not blind
replay with a new key. An uncertain native Close may be retried with its original
key to observe whether that exact document closed. No edit-job rollback applies
to document closing.
