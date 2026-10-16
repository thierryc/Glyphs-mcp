# Companion Tasks

Tasks monitors workflows in the existing native desktop app, with a guarded
recovery route for abandoned tasks. Setup retains
installation, server controls and health warnings. Task lists and history live
in Tasks. The app menu, menu-bar popover, status-icon contextual menu and Dock
menu all use **Show Tasks** and open the same window.

The sidebar badge counts unviewed tasks, not unresolved decisions. Opening a
task marks it read; opening Tasks does not mark all tasks read. Closed history
present on first use starts read. Read markers are local to the installation;
they do not modify workflow revisions, recovery, or agent authorization. Bold
titles identify unread items without an additional dot. Normal closed tasks
have no Completed badge. Health indicators separately describe the MCP listener
and whether a Glyphs 4 process is running; running does not prove bridge access.

Inactive selection uses a faint, opaque blend of the system control background
and inactive selection color, with a subtle outline. The native List retains
selection and focus handling. Focused selection and Increase Contrast use the
system highlight without a custom row background. The lighter treatment adapts
to light and dark appearances and does not affect task state.

## Inventory and decisions

`list_tasks(cursor=0, limit=50)` and authenticated loopback
`GET /internal/tasks` share a passive projection. All unresolved tasks are
included on every page; only closed history is paginated. Workflow and job
entries are correlated by job identity. Unmatched jobs remain visible for
diagnosis. An ID/creation/closed/evidence-revision index lets the companion count unread tasks
without loading all history details. Neither endpoint polls native operations,
executes scripts, saves, closes tasks, or issues action tokens.

The agent uses `get_edit_workflow(workflowId)` to retrieve current choices and
tokens before responding, even from a new conversation. Job-only entries use
`get_job` for diagnosis. Normal workflow decisions stay in the agent, with
existing guards and recovery semantics. Never restart a script
to recover a missing conversation. Partial execution and unverified outcomes
remain explicit; a failed Git checkpoint does not erase a successful font save.

Tasks uses the existing native secondary capsule buttons. A valid recorded
Codex origin offers **Open Conversation…** above the prompt area. The prompt
remains available alongside the link. Claude Code, missing or invalid origins,
and conflicting associations explain why no usable link is available, without
guessing a destination. A failed URL opening shows an inline explanation and
retains both the prompt and the button for retrying.

**Prompt for the Agent** has a native **Review / Close task** segmented control.
Both choices display their exact selectable handoff text in the system
monospaced font. A small **Copy** icon in the header copies the displayed text;
a checkmark confirms success. Changing the intent clears copy feedback, and
selecting a different task returns to Review. The close prompt requests fresh
state and blockers, explains cancellation limits and existing recovery choices,
and waits for the user's decision in the agent. Selecting it or copying it does
not cancel, close, hide, save, restore or mutate a workflow.

The task row's contextual menu also offers Copy Request; for the selected task,
it copies the current intent. Copying prepares text and sends no message.
History shows retained timestamps and outcomes, without inventing a past event
stream. Closed tasks retain their history without offering a new close prompt.

**Clear Closed History…**, below the task list, confirms before hiding all
currently closed entries, including unloaded history pages. Cleared entries no
longer contribute to the unread badge or history pagination. Refreshing and
reopening the app retain the choice; newly closed tasks remain visible. A
cleared task that reopens is visible again. The native controls retain their
existing style; the confirmation dialog explains the 30-day policy without
repeating it below the controls. Synchronization and compatibility notices
remain visible when action is needed.

### Thirty-day cleared-history retention

The companion persists clear dates and an ordered, bounded outbox alongside
its existing local hidden IDs. `POST /internal/task-history` accepts authenticated
loopback `clear` or `restore` requests for up to 100 exact task IDs, optionally
bound to the inventory's `historyRevision` evidence digest. The full index
includes that digest, so unloaded pages are covered without guessing revisions.
No new public MCP tools or workflow schema changes are introduced.

The sidecar records the first accepted clear time; retries never extend it.
Offline requests survive companion shutdown and sync on subsequent refreshes.
The UI explains when synchronization is pending or an older sidecar needs an
update. The 30-day period starts at server receipt, so an offline clear cannot
cause an unexpectedly early deletion. Legacy hidden IDs receive a fresh grace
period at adoption, with no inferred historical date.

**History Options → Show Cleared History** cancels pending retention. Restoring
then clearing again starts a new period. Within the local grace period, showing
history is immediate even offline. Older cached entries wait for server
acknowledgment. Expired history cannot be restored for the same evidence; its
underlying diagnostics remain accessible by the original job/workflow ID.

The process-lifetime sidecar worker checks at startup and hourly, independently
of the companion. Inventory reads remain passive and never trigger cleanup.
Cleanup holds workflow/dispatch/service/job-store locks, respects installation
reservations and active workers, and requires reachable Glyphs with explicit
zero native activity. It rechecks closure, blockers, unresolved recovery, exact
job/workflow evidence and native operation state. Missing or uncertain evidence
postpones cleanup. Reopening or changed evidence cancels the old retention entry
and invalidates any expired exclusion marker.

Only `jobs/task-history/ledger.json` is rewritten, under an interprocess file
lock with atomic replacement. Each pending entry contains a history summary,
evidence digest and clear time. After 30 elapsed days and successful checks,
that summary is removed and replaced with an ID-keyed digest/expiry exclusion
marker. This prevents old canonical records from repopulating Tasks history.
A failed/interrupted write leaves the old ledger valid and is safe to retry.

No job or workflow record, diagnostic file, receipt, snapshot, checkpoint,
recovery artifact, archive marker or font file is deleted or modified. Original
Unverified outcomes remain intact, including for archived interrupted jobs.
Idempotency keys and action-consumption evidence remain intact. This is history
retention, not a complete erase or disk-space purge of underlying records.

## Abandoned-task recovery

**Recovery Options…** opens a native sheet below the agent prompt. It fetches
current state through authenticated loopback `POST /internal/task-recovery`.
The narrow facade offers only existing Keep/finish and cancellation choices,
with current workflow revisions and action tokens. Save, Restore, selective
Undo, Apply, Run, and unknown-outcome acknowledgment are not exposed here.

**Close Without Saving** keeps current changes and ends temporary recovery;
typed edits explain the end of selective Undo separately from native Undo.
**Cancel Task** cancels pending work or an unapplied preview. **Cancel Remaining
Work** is offered only when the existing script lifecycle supports it; partial
changes and unresolved recovery remain visible afterward. Cancelling a blocked
request detaches that request without resolving or starting its earlier owner.

Inspection reconciles existing native operations without resuming ready or
interrupted preparations or advancing blocked requests. Dispatch rechecks the
allowed choice under the workflow and dispatch locks, then uses the existing
respond path, reservation gate, token consumption, and native ownership guards.
Uncertain/unavailable outcomes have no closing choice and explain the need to
check again. They are never force-deleted or acknowledged automatically.

### Archive interrupted records

For an orphan interrupted job, Recovery Options can offer **Archive Interrupted
Task** as a neutral native capsule. Its visible consequences explain that this
moves the record into Recently closed tasks with an **Unverified** outcome. It
does not cancel execution, save, restore, release recovery, or confirm success.
The original warning remains visible, including after archiving.

The authenticated loopback recovery route accepts exactly one identity:
`workflow_id` for existing workflow actions, or `job_id` for archive inspection
and dispatch. No public MCP tool or workflow schema changes. Every archive
dispatch rechecks a server-issued token bound to the complete job evidence,
under the workflow, dispatch, service, and job-store locks, and respects the
installation reservation gate.

Archiving requires an interrupted job with no owning workflow or blocker
reference, no pending worker or native activity, and no unresolved recovery or
save ownership. Glyphs must be reachable, explicitly report zero active
operations, and confirm that the exact native operation is absent. Unknown or
failed reads refuse archiving. Script and checkpoint restore jobs retain their
existing recovery paths and cannot be archived through this shortcut. An
existing native operation must be reviewed in the agent, even if it reports
completion. Activity that begins or evidence that changes after inspection
invalidates the offered choice.

The separate `job_*/task-archive.json` marker records the evidence fingerprint,
archive time and unverified outcome. The original `state.json`, errors, request,
reports, receipts, and artifacts remain untouched. Execution guards continue
to use the original job status. Passive inventory projects a matching marker
as closed/archived with an Unverified label and a persistent archive receipt.
New job evidence or a new workflow/blocker association returns it to attention.
Check Again reconciles a lost archive reply without repeating an operation.
Clear Closed History can hide archived rows and schedule their history summaries
for 30-day retention, while preserving the original records and Unverified outcomes.

The sheet shows consequences before the action. It retains authoritative
closure text until dismissal; cancellation in progress is not a closure receipt.
The top-left X dismisses only the sheet and has an accessible close label and
Escape shortcut. The footer separates Check Again from the task action.
Cancellation uses a red native destructive capsule; keeping changes without
saving remains neutral. There is no second Cancel dismissal button. Filenames
stay compact, with the full path available on hover. Material warnings and
recovery consequences remain visible; the generic instruction is omitted when
an explicit action and its consequences are already shown.
Failed/lost replies remove stale buttons and require Check Again, which can
reconcile external completion without replay. Older sidecars explain that an
update is needed. Viewing Tasks, opening the sheet, and copying prompts never
save, restore, apply or run a script. No MCP tool signatures or persisted
workflow schemas change.

## Optional conversation capture

The lean builder includes `sidecar/task-origin-hook.py`. Hook activation is a
separate agent configuration step; building or opening the companion does not
enable it or grant hook trust.

Configure a command `PostToolUse` hook for the exact managed Glyphs MCP
`start_edit_workflow` tool. For example, the command-hook group is:

```json
{
  "matcher": "mcp__glyphs[-_]mcp__start_edit_workflow",
  "hooks": [{
    "type": "command",
    "command": "\"/path/to/lean-v2/runtime/bin/python3\" -B \"/path/to/lean-v2/sidecar/task-origin-hook.py\" --agent codex",
    "timeout": 3
  }]
}
```

Place the group under `hooks.PostToolUse` using the client's normal hook setup.
Use `--agent claude_code` for Claude Code. Codex hooks require normal review and
trust of the exact definition. Verify a real desktop MCP call after deployment;
tool wrappers or custom server aliases that do not emit the expected event
leave the Copy Request fallback available.

The adapter accepts only successful Glyphs MCP starts, normalizes Codex's
structured result and Claude Code's JSON text, and pairs the returned workflow
ID with the hook's session ID. It reads the existing launch-agent port/token
configuration and registers that metadata through authenticated loopback
`POST /internal/task-origins`. Proxies and redirects are disabled for this
request. It never reads transcripts or guesses from titles, font names, or
working directories. Missing or older services do not block the agent call.

Associations are stored in `jobs/task-origins/`, separately from workflow state.
Identical registration is idempotent. A conflicting registration retains the
original ID and flags the association; the companion offers Copy Request rather
than selecting a destination. Polling and viewing a task do not adopt its origin.
Only a fixed `codex://threads/<validated UUID>` link is constructed. Claude
Code's generic URL starts a new session, so it is not used to promise reopening
the original conversation.

## Offline and compatibility

Retain the last snapshot and unread count when disconnected, with an explicit
stale indication. An older sidecar reports that an update is required rather
than showing a falsely empty task list. Navigation and copying remain usable;
the agent must fetch fresh lifecycle state before taking an action.

No deployment, hook activation, installation, or runtime restart is performed
by the Tasks view or by its tests.
