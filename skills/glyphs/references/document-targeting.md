# Reuse a known live document ID

Use the verified connection context already available; load
[connection setup](connection-session.md) only if missing or changed. Start with
the retained ID for the intended font on this connection. Discover the intended
font once with `list_documents` only when that binding is absent or invalid;
resolve its exact path or other explicit user context and retain the returned
`document_id`. Never obtain an ID from a native verification helper or guess one.

For subsequent reads of the same font, call `read_entities` directly with that
ID. No preceding document list is required. Selection, dirty state and font data
remain live: remembering identity does not cache contents or imply a clean source.
Existing job preparation, source guards and Undo/discard rules still apply.
Switching skills, returning from coding to font work or receiving a follow-up
does not invalidate this binding. Do not list documents just to reconfirm it.

An ID identifies one native font instance within one bridge lifetime, not a path,
window position or foreground slot. Switching windows does not change its target.
Closing and reopening the same file creates a new ID. A bridge/Glyphs restart
invalidates old IDs. A transport reconnect alone is not proof that Glyphs restarted.
Do not share an ID across MCP connections, even when their font paths match.

| Situation | Next call |
|---|---|
| Same intended font, valid retained ID; selection or foreground changed | `read_entities` with that ID and the newly needed fields |
| Missing glyph, bad field or invalid kerning selector | Correct that request using the same document ID |
| `document_not_found` or known bridge/Glyphs restart | `list_documents`, then resolve the original intended font explicitly |
| Explicit new target or ambiguous current/frontmost intent | Resolve that intent; discover only the needed target |
| Offline code/docs work or connection-only diagnostics | No document discovery |

If `read_entities` returns **`document_not_found`**, discard that retained binding,
call `list_documents`, and resolve the original intended font again. A reopened
copy at the intended path may be selected explicitly from that fresh result.
If the intended font is absent or ambiguous, report that and obtain a clear target;
never silently substitute another open font or reuse the stale ID. Do not retry
indefinitely. Report that any recovered read belongs to a new live font instance.

For `target_not_found` (for example a missing glyph), `unsupported_read`, invalid
fields, node limits or other unrelated errors, keep the document ID and resolve
that actual error. Listing documents again is not a recovery for missing glyphs.

An explicit change of target requires resolving that target. Treat “the current/
frontmost font” as a fresh targeting question when the previously identified font
may no longer be intended. `read_entities` does not select the frontmost document;
`list_documents` advertises `isCurrent` with negotiated `document.context.v1`: true
identifies Glyphs’ native current font, false means another/no current font, and
null means native evidence is unavailable. Require exactly one true marker for
an explicit current-font request; do not infer it from list order. If the capability
is missing, update the bridge, sidecar and skills together. If current evidence
is unavailable or ambiguous, obtain an explicit target. This is Glyphs’ current
font, including when a utility window is frontmost, not a macOS window-order guess. Window
activation alone must never silently redirect a read bound to an explicit font.

Use the current private bridge, sidecar and skills together. Missing required
capabilities or identity evidence means update the installation, not a fallback
workflow for an earlier private build. This change adds no tool or document-data
cache, no polling, and no implicit save.
