# Local Git checkpoints for saved fonts

Require `font.checkpoints.v1` in `get_status.workflowCapabilities`. Historical
restoration additionally requires `font.checkpoint-restore.v1` and
`checkpoint_restore` in `jobKinds`. A missing capability is an installation gap.

Checkpointing is opt-in for one project, using `.glyphs-mcp.json`:

```json
{"schemaVersion":1,"gitCheckpoints":{"enabled":true}}
```

The app exposes **Create a Git checkpoint when saving through MCP.** Enabling
it authorizes local baseline and result checkpoints for that project. It does
not authorize extra Saves, Git initialization, other commits, or pushing.
AGENTS.md documents this policy; the runtime reads only the versioned config.
The **Font project with Git checkpoints** template explicitly initializes a new
repository during project creation. It includes no font.

Before an authorized edit, the service ensures that the exact saved font has a
Git baseline. A matching HEAD is reused. A clean font receives no additional
Save. Dirty/new fonts use the existing authorized Save/Save As/manual workflow.
Preparation and preview do not create checkpoints or execute edits.

After a verified MCP Save, the service commits only the intended `.glyphs` or
whole `.glyphspackage` and its action records. Unrelated staged files stay
staged. Keep without saving creates no result checkpoint and ends the existing
workflow recovery offer. Native Undo/Redo remains available for ordinary typed
edits. Baseline checkpointing does not extend an expired recovery offer.

Saving and Git have separate outcomes. **Font saved; checkpoint failed** means
that saving succeeded. Use the offered **Retry checkpoint without saving** or
`save_document(document_id=original_id, retry_checkpoint_job_id=receipt.checkpoint.retryJobId)`.
Do not rerun the edit or repeat Save. Reconnects reconcile existing save/job IDs.
A conflicting index, active hook, byte-transforming attribute, or changed saved
file fails explicitly. Do not disable hooks, remove someone else's Git lock,
or reset an index to work around a rejected checkpoint. A crash can leave a Git
lock that needs manual reconciliation; this is not a crash-recovery system.

## Read history on demand

Use the retained exact `document_id`; one selector per call, with
`fields=["checkpoint"]`. Responses carry a `checkpoint` object.

- Recent history: `{"kind":"checkpoint_history","limit":20}`. Pass the
  returned `nextCursor` as `cursor` for another page. A changed branch invalidates
  the cursor; restart from the first page. No history scans occur during polling.
- Actions: `{"kind":"checkpoint_details","selected":"FULL_REVISION"}`.
  This returns recorded requests, exact script/parameters when applicable, scope
  references and actual execution/verification evidence. Older ordinary Git
  commits may have no MCP action record.
- Scope: `{"kind":"checkpoint_scope","selected":"FULL_REVISION",
  "reference":"RETURNED_SCOPE_REFERENCE","offset":0,"limit":100}`.
- Compare: `{"kind":"checkpoint_compare","before":"FULL_REVISION",
  "after":"FULL_REVISION","offset":0,"limit":100}`. Use `nextOffset`.
  Add `file` with a returned changed path for bounded before/after text.

Read pages contain at most 100 entries. Text files are capped at 1 MiB per side.
Checkpoint writes support at most 100,000 files and 512 MiB of font data;
action records are capped at 8 MiB, combined action/scope evidence at 64 MiB.
Oversize requests fail explicitly. These Git-specific bounds do not change
native script targeting or typed-edit limits.

## Restore a historical version

A clear restore request authorizes execution. Explain the coverage before
acting: **Restore replaces all later changes in this font, including unsaved
edits, and clears Undo history. It does not save.**

Use `start_edit_workflow` with `kind="checkpoint_restore"`,
`options={"revision":"FULL_REVISION"}`, an exact retained document binding and
stable `idempotency_key`. `mode="apply"` executes under the restore request;
`mode="preview"` waits for the existing Apply action. Reconcile outstanding jobs
first. The service loads the selected version through Glyphs, leaves the current
file untouched and returns the fresh binding in `document` / `documentAfter`.
Use that authoritative binding afterward. Never write an open font's file from
Git, reset the repository, substitute another document, or replay original Python.

Offer Keep or separately authorized Save. There is no selective Undo for the
whole-font historical reload; choose another checkpoint explicitly if needed.
A later authorized Save creates a new checkpoint recording the restoration.
History remains intact. An uncertain reload must be reconciled, never replayed.

Action records live at `.glyphs-mcp/actions/<font-path-hash>/<save-id>.json` in
the same commit as the font. Scope references resolve in that commit. Execution
success is separate from intended-result verification. One Save can include
several agent actions and manual changes; never attribute the entire diff to the
LLM or invent verified counts. Records contain no chat transcript or hidden reasoning.
