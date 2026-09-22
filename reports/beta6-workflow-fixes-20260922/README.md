# Beta 6 workflow fixes — September 22, 2026

Both requested regressions passed installed-client retesting with sidecar
`6fe1d1da74ca` and the unchanged bridge `c288fa8ec5bf`, Glyphs 4.1 (4107),
Claude Desktop 2.2553.13 and Cursor 3.21.18. These results supersede the
corresponding failures in the earlier save UI retest. They do not establish
signed-distribution or cross-machine acceptance.

## Changes

- Every workflow result supplies a compact JSON control reference in a second
  model-visible text block, including the workflow ID, revision, state, polling
  flag and offered action tokens. Card state reads and async completion update
  the conversation with the same reference.
- Tool descriptions and mirrored skills retain that reference internally,
  refresh before later replies, and distinguish Preparing from Applied.
- Cards read authoritative state on initialization, notifications and reopening.
  Choices stay disabled until reconciliation; reads never replay mutations.
- Tool-call deadlines allow 120 seconds for host permission dialogs. Successful
  state reads clear superseded transport errors; server validation errors such
  as Save As collisions remain visible.
- Corrected the release-summary inventory from nine to twelve tools and brought
  the maintained release instructions forward to Beta 6/build 48.

## Actual Claude conversation

Conversation: `0c235273-f175-41c3-a674-75cab19b2c49`.
Used only the disposable Claude Beta6 Save font, initially 600 on disk, changed
through the native width field to 610 without saving. No workflow identifiers,
tokens or JSON were supplied in the conversation.

1. Requested A width +2 in Regular, applied, scoped to this disposable font.
   The first document-discovery call expired while its host permission prompt
   was unanswered during a long computer-control stall. A read-only retry
   succeeded. Claude corrected its initially invalid kind/options from the
   server's validation errors, then offered the dirty-font save choices.
2. Replied exactly **Save and continue.** Claude retained the workflow, saved
   the original 610, applied 612, read the async result and accurately reported
   Applied and unsaved. Native MCP reads independently confirmed 612 live;
   source parsing confirmed 610 on disk. See `claude-prerequisite.json`.
3. Replied exactly **Save the font.** Claude refreshed the same workflow and
   submitted the offered save token without asking the user for identifiers.
   It reported Saved; the card showed **Font saved.**. Native receipt, source
   parsing and document discovery confirmed 612 on disk and dirty=false.
   See `claude-final.json`.

Host tool permission prompts were answered through the normal client UI.
The test used no save/apply helper to substitute for the conversational actions.

## Actual Cursor remount and slow permission

Reopened the prior test's historical start-tool card in **MCP read tools report**.
The retained snapshot said Preparing and offered Cancel preparation even though
the workflow had since been saved.

- On mounting, the new card immediately requested `get_edit_workflow` through
  Cursor's normal MCP Apps permission prompt. The read approval was deliberately
  delayed beyond the old 15-second deadline.
- The stale Cancel control was disabled while the read was pending. After
  approval, the card showed **Font saved.**, with no action row and no stale
  timeout error.
- Collapsing and reopening the tool activity created a new webview and another
  host read prompt. After approval it again showed **Font saved.**, without
  presenting actionable stale choices or replaying the mutation.

Cursor's host permission prompts remain part of its client behavior. This pass
qualifies remount/read recovery; it does not claim a new Cursor model-driven
text-save sequence or every mutation scenario in that host.

## Automated and installation evidence

- Full local release gate: 2,149 Python tests passed, one skipped; 203 macOS
  installer tests passed; deterministic payloads, both private runtimes,
  twelve-tool inventory, eleven mirrored skills, docs and unsigned app passed.
- Focused workflow/card suite: 26 passed. The text-only transport test never
  reads structured content and verifies separate prerequisite and final saves.
- The actual bundled JavaScript fixture covers delayed permissions, stale
  remounts, lost responses without mutation replay, visibility refresh, async
  model-context updates, approval guards and server/card wording.
- The release-summary correction was checked separately after the full gate;
  it changes reporting only. The guarded publisher will rerun the full gate.
- Installed the verified MCP component through the transactional installer,
  retaining its backup. Fresh status matched the candidate fingerprint.

`candidate-identity.json` and `source-fingerprints.json` identify the runtime
qualified here. Compressed full-gate output and focused test output are retained
alongside the bounded native evidence.
