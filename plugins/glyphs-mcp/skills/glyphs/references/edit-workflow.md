# Conversation edits

Reuse the intended document ID and connection. Require `edit.workflow.v1` in
`workflowCapabilities`; keep the ordinary job capability and scope checks.
Call `start_edit_workflow` with the existing mutation fields, `mode="apply"`
for requested edits or `mode="preview"` for preview requests, and one unique
idempotency key retained for that request. Never replace a timed-out request
with a new key. Compilation and export use the existing job lifecycle.

Use the standard MCP App when the host supports it. Do not select rendering by
client name or invent separate Claude/Cursor/Codex interfaces. If cards or their
tool calls are unavailable, present the returned text and use the same tools.
Supported native choice controls may present these same choices in a text-only
host; plain conversation is always sufficient. No installed skill is required
to use the server's tool descriptions and returned choices.

- Saved and clean: preparation begins immediately. Complete reports without
  warnings, unavailable/skipped targets or overwrite approvals apply automatically.
- Dirty: explain that **Save and continue** saves the entire font, including
  existing unrelated work. It resumes this retained request after verification.
  Offer **Save As**, **I'll save in Glyphs**, or **Cancel** as alternatives.
- New font: offer **Save As** or manual saving. For Save As obtain an absolute
  folder and filename, show the resolved new destination, and use the offered
  destination action. Existing files are never overwritten.
- Manual save: keep the workflow and use **Check and continue** afterward.
- Preview or report review: inspect the complete `get_job` report, explain any
  skipped/unavailable targets and warnings, and reuse original edit authorization
  where it covers the proposal. Never describe partial coverage as complete.
  Dimensions overwrites still need the exact old/new approval entries.
  Use **Changes ready to review.**, **Apply changes**, and **Discard preview**;
  when warnings need review, say **Some changes need your review.**
- Applied: say **Changes applied. Save your font to keep them.**. Saving the result is a separate
  authorization. **Save font**, **Save As**, and **Undo these changes** use
  the existing native guards; whole-font saving can include subsequent edits.
- Saved: say **Font saved.** Do not describe discard windows or internal jobs.
- Discarded: say **Changes discarded.** This also covers previews that were never
  applied; do not claim an edit was undone without verified evidence.
- Preparing: say **Preparing changes…**; never report application before it is verified.
- Previous edit: offer the returned save or undo choices; retain one next request only.
- Outdated: describe the returned reason and offer preparation again, with a
  prerequisite save only if authorized. Never silently refresh a stale patch.
- Uncertain or restarted: offer **Check result**. Never replay mutations
  or saves, infer success from a timeout, or submit a replacement job blindly.

Map natural-language replies such as “save and continue”, “save it first”,
“I'll do the save”, or “discard this proposal” to the matching offered action.
Retain the compact JSON control reference in tool text and card context updates;
it supplies the workflow ID, expected revision and server-issued action tokens
even if the host omits structured data. Use these internally in
`respond_edit_workflow`; never make users type identifiers, tool names or JSON.
On a later reply such as “Save the font”, read `get_edit_workflow` first because
the worker or card may have advanced, then revalidate the intended
choice. Reuse existing scoped authorization; do not ask the same question twice.
Ambiguous document, destination or save scope still requires clarification.

Closing a card does not cancel authorized work. Poll an active workflow only
when needed for the displayed conversation; the server itself continues work.
When `poll` is true, read until the current choice or outcome before reporting
completion. A Preparing result establishes progress, not application.
Do not keep polling an unchanged waiting choice. Every response contains both
useful text and structured state, so a failed UI cannot strand the request.
