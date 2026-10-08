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

Typed edits and scripts share Keep, Save and their appropriate recovery action. Scripts use their own Run action under
task authorization, as described at the end and in the shared contract.

For a known connection and document, use this minimal sequence:

1. Read only missing target information, then start one workflow. Do not repeat
   `get_status` or `list_documents` for each edit or focused skill.
2. Reuse the returned state and actions. Poll `get_edit_workflow` with its default
   compact response only while `poll` is true. Do not add `get_job` or health
   reads unless a complete report or a connection problem actually requires them.
3. Verify the intended result with bounded fresh reads of targets and relevant
   controls. Report observed changes separately from execution completion.
4. Use the offered Keep, Save or recovery action under its actual authorization.
   Refresh the workflow before acting on a later reply; after restoration, use
   its fresh document binding. An uncertain action is reconciled, never replayed.

Load **Script details** once when requested and reuse it only for the same
workflow, document binding, job and request fingerprint. Compact responses omit
source and output; omission preserves matching evidence, while explicit empty
values replace it. Refresh open details when execution finishes. A changed
identity clears cached evidence. Display caching never authorizes Run, Save or
Restore, and a reconnected or newly visible card still reconciles fresh state.

An edit remains active while its native Undo groups and temporary precision
settings finish closing/restoring. Keep polling the same workflow; a completed
target count alone is not a finished result. Wrapper cleanup yields between
targets, but an individual native call or script invocation cannot be interrupted.
Do not start a replacement edit, save or offer Keep before the result is ready.

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
  Use **Changes ready to review.**, **Apply changes**, and **Cancel preview**;
  when warnings need review, say **Some changes need your review.**
- Applied: say **Changes applied.** Offer **Keep changes without saving**,
  **Save font**, **Save As**, and **Undo these changes**. Keep closes the workflow
  and its selective Undo offer without saving; native Undo/Redo remains available.
  Saving requires separate authorization and includes subsequent edits.
  Selective Undo stops on conflicting later edits. Keeping a dirty font does not
  satisfy a later task’s saved/clean prerequisite.
- Saved: say **Font saved.** Do not describe discard windows or internal jobs.
- Discarded: say **Changes discarded.** This also covers previews that were never
  applied; do not claim an edit was undone without verified evidence.
- Preparing: say **Preparing changes…**; never report application before it is verified.
- Previous edit: identify `blockingWorkflowId` when available and use its offered
  resolution. Typed blockers also offer manual Keep, including direct jobs without
  an original workflow. Never automatically settle a blocker; retain one next request only.
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

Python script workflows follow [the shared execution contract](python-scripts.md).
Preparation and polling never execute Python. The agent uses the revision-bound
Run action under the original task authorization without requiring code review,
a human click or another Run question. Explicit previews wait. Write-only and
review-only requests do not authorize live execution; script writing includes review.

Require `script.native.v1`. Clean saved fonts skip Save. Dirty fonts require
an authorized **Save and run** or manual saving; new fonts use Save As/manual
saving and fresh validation. Failed/uncertain saves never start Python.

Lead with font, intended change and scope, show the execution warning once,
and keep exact source/params in optional **View details**. Text-only **Show
script** uses `get_edit_workflow(include_review=true)`; default polling stays
compact. Successful execution and completed callbacks do not verify the result.

After success, offer **Keep changes without saving**, **Save font**, and available
**Restore saved version**. Partial failure/cancellation offers Keep and restoration.
Restore reloads the whole unchanged baseline, replacing all later unsaved edits
and clearing Undo history. It never saves or reruns code; use the fresh document
binding. Keeping or saving ends the restoration offer. A clear restoration request
authorizes the action; clarify only ambiguous scope. Unknown results use **Check
result**, never automatic replay. No native dialog or external page is required.

If another request is blocked by this script, use its `blockingWorkflowId` to
resolve the original workflow's offered Keep, Save or Restore choices. Script
blockers do not offer typed Undo. Failed/cancelled scripts with partial edits
remain unresolved until explicitly kept or restored. Restoration availability
uses a short display cache; the unchanged baseline is checked again at Restore.

## Automatic Keep

New successful typed-edit and script cards default to a visible 30-second Keep
countdown. Keep ends the workflow’s recovery offer without saving. Older typed
workflows remain manual. Honor **“wait for my answer”** with `auto_keep=false`
on start or the offered **Wait for my answer** action; carry that directive into
later requests until changed. A failed or uncertain opt-out leaves the card locally
paused while its existing request is reconciled.

Cards label that same `wait_for_answer` action **Pause countdown** during the
countdown and **Turn off automatic Keep** beforehand. Keep the conversational
phrase **Wait for my answer** as an alias; do not require users to repeat it.

The countdown runs only on a visible, connected, freshly reconciled successful
result card. Details, hidden cards and reconnection reset elapsed time. Failed,
partial, uncertain and blocked outcomes never automatically Keep. Text-only clients
remain manual; elapsed time does not imply an answer. There is no timed Run, Save,
Undo or Restore. Cards record timed completion as such, not as a human click.

## Portable card presentation

Use the server's optional action `presentation` metadata for main choices,
**More options** and automatic Keep controls. All offered actions remain in the
machine-readable control reference; text responses list main and secondary
options separately. One **View details** disclosure contains the full path,
request, script evidence and diagnostics. Warnings and recovery consequences
stay visible. Do not confuse a cancelled script with partial edits with a settled
request that needs no action.

Visible cards use `uiRefreshIntervalMs` to refresh processing every 1.5 seconds
and pending choices/recovery every 5 seconds. This does not change the agent's
`poll` instruction or require polling while awaiting an answer. Background reads
preserve a countdown only when identity and revision remain unchanged. Opening
View details or More options pauses it; return/reconnect starts a fresh countdown.

On `stale_workflow_action`, read the same workflow, present its current state and
choices, and never repeat the rejected mutation automatically. Cards remove the
obsolete controls, clear the stale warning on successful reconciliation and offer
**Check status** when reading fails. Text-only clients use the same lifecycle;
the plugin cannot remove historical messages or host-owned controls. Use host
capabilities rather than client-name-specific behavior.

## Preparation

When negotiated internally, widths, Dimensions, glyph colors and coordinate-only
`outline_edit` node updates prepare from bounded live reads and detached target
copies. Preparation never edits the font. These jobs retain saved/clean prerequisites,
target guards and selective recovery; the agent chooses no additional mode.
Mixed or other outline operations and algorithmic jobs retain external preparation.
The runtime reports preparation errors instead of silently switching routes.

## Optional project checkpoints

When enabled in project settings, authorized Saves also create local Git checkpoints.
Keep without saving creates no result checkpoint. Saving and Git failures are
reported separately; retry only the checkpoint. See [Git checkpoints](git-checkpoints.md)
for bounded history reads and whole-font historical restoration through Glyphs.
