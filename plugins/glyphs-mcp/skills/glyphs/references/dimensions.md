# Dimensions reference notes

For conversation edits, use the [shared edit workflow](edit-workflow.md)
with these same request fields when `edit.workflow.v1` is advertised. The
low-level job examples below describe operation scope and existing guards.

Dimensions are per-master reference notes shown in Glyphs' sidebar palette.
They do not measure or change outlines, hinting stems, metrics or exported fonts.
Use task-supplied or task-established values; never invent values to fill blanks.

## Read freely

Require `master.dimensions.read.v1` in the retained connection's read capabilities.
Use `read_entities` with 1–4 exact master selectors and requested field
`dimensions`. Master discovery remains a separate `masters` page; Dimensions
are not available on pages. Reads work on dirty and unsaved fonts without Save.

Each master returns `items`, `total`, `returned` and `complete`. Items include
`key`, readable `label`, `script`, `present`, numeric `value`, exact `storedValue`,
`valid` and `editable`. Shared Latin/Cyrillic references have shared keys. The
catalog includes 60 native fields, including uppercase/lowercase diagonals,
Arabic, Myanmar, Thai, Lao, Han, Kannada and Khmer references. Numbered references
retain their native palette numbering rather than assigning guessed meanings.

Missing keys are unset. Zero is set. Glyphs' palette stores typed numbers as
text; reads interpret numeric text but retain it verbatim in `storedValue`.
Malformed stored data remains present, invalid and uneditable; correct it in
Glyphs rather than treating it as a blank. Unknown fields are read-only and
preserved. `editable:false` can also mean the installed Glyphs build has not
been qualified for writing.

## Fill freely; ask only before overwriting

Require `master.dimensions.edit.v1` and `dimensions_edit` in `get_status`.
Writing is qualified on Glyphs 4.1 build 4107; other builds retain read access.
The saved-clean-source requirement and existing twelve-tool job lifecycle apply.
Never save merely to satisfy preparation; ask the user to save or obtain separate
Save authorization if needed.

Prepare `start_job(kind="dimensions_edit")` with `options.changes`, a list of
1–100 entries containing exact `master`, `key`, and numeric `value`; `null`
clears a value. Do not provide `delta` or `glyphs`. Inspect the complete
`get_job.report.targets`, with master names, labels, exact before/after states
and `fill`, `overwrite`, `clear` or `no-op` classification.

- Read and populate unset fields freely within the current task. Blank-only
  jobs need no additional confirmation before `apply_job`.
- Before replacing or clearing any existing value, show the font, master,
  field label and exact old/new values, then wait for explicit approval in the
  conversation. An earlier broad edit request does not approve an unseen
  overwrite proposal.
- Only after that reply, pass the exact `report.requiredOverwrites` entries as
  `apply_job.approved_overwrites`. Entries contain `master`, `key`, `before`
  and `after`; each state contains `present` and exact stored `value`.
  This records assistant-reported approval, not authenticated human consent.
- A mixed batch waits as a whole. If the user declines an overwrite, discard
  the proposal and prepare a reduced job. Its remaining blank fills remain
  authorized; any changed overwrite proposal requires fresh approval.
- A stale source or changed target invalidates the proposal. Reread and prepare
  again. A formerly blank field that is now populated requires overwrite approval.
  Reconcile uncertain writes using the existing job ID; never replay as a new job.

Application changes only the selected notes and leaves the font unsaved. Undo
and Redo are document-level for these metadata edits. `discard_job` restores
exact values and originally absent containers while preserving unrelated data.
Use `accept_job` only when saving the entire document has separately been
explicitly authorized. Rebuild the bridge, sidecar and skills together when
these capabilities are absent; do not substitute arbitrary scripts.
