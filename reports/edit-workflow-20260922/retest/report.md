# Save UI retest — September 22, 2026

Release recommendation: **hold Beta 6**. Real Claude and Cursor card saves work,
but Claude's natural-language final save failed, Cursor exposed stale-card and
permission-timeout UX, and Codex's inline check is blocked in this task.

## Candidate and method

Retested the unchanged installed Beta 6 candidate, build 48, with Glyphs 4.1
(4107). Loaded sidecar hash `fd468ae49ee2c8da71db42a78c57fc775138937bbc51a1a6410aac78eaae4839`
and bridge hash `c288fa8ec5bfe426168297dc192da457692ce77e61fa56901c46a5db06b40ebb`
match the parent report's installation evidence. This is qualification of the
installed unsigned candidate, not a published release.

Client versions from the installed app bundles:

| Client | Exact version | Test status |
| --- | --- | --- |
| Claude Desktop | 2.2553.13 | Standard card saves passed; natural-language final save failed |
| Cursor desktop | 3.21.18 | Card saves passed with host permission/UI issues; text follow-up blocked by account usage limit |
| Codex desktop | 26.915.31945 (9922) | Inline test blocked; no claim of unsupported MCP Apps |

Created separate `Claude Save UI`, `Cursor Save UI`, and `Codex Save UI` disposable
fixtures from `headless-preview-minimal.glyphs`; initial paths, hashes, and client
versions are in `baseline.json`. All mutation/save actions under test used the
actual client card or conversation. The snapshot helper only reads documents,
layers, source bytes, and persisted workflow evidence. It does not invoke save,
apply, or workflow reconciliation. Fixtures use A and master
`11111111-1111-4111-8111-111111111111`.

## Claude card sequence

1. Started dirty: 610 live, 600 on disk. Claude discovered the explicit document
   and started +2 in apply mode; the other disposable font was frontmost.
2. The standard card showed scope/path and all four prerequisite choices.
   Save As opened inline with an absolute folder, filename, and resolved path.
   Back returned to the existing workflow without saving.
3. I'll save in Glyphs showed Check and continue. Checking before saving returned
   to the prerequisite choices; it did not prepare or apply the edit.
4. One Save and continue clicked in the card saved 610 and automatically applied
   612. Native evidence confirms 612 live, 610 on disk, dirty, state `applied`.
   No further model turn was needed.
5. Final Save As to the existing original file was rejected visibly:
   “The Save As destination already exists; v2 never replaces it”. The workflow
   stayed applied with 612 live and 610 on disk.
6. Final Save As to `Claude Save UI-final.glyphs` succeeded: 612 live/on disk,
   clean, state `saved`. The card showed the new path and verified completion.

Evidence: `claude-before.json`, `claude-after-save-continue.json`,
`claude-save-as-existing-rejected.json`, `claude-final-save-as.json`.

## Claude text fallback failure

Started a second clean-font +1 workflow from conversation. The card correctly
reached 612 → 613, Applied in Glyphs · Not saved. The assistant's prose combined
“Applied” with the initial Preparing state and only Cancel preparation; it had
not refreshed the async result before reporting completion.

Sent exactly **“Save the font.”**, without IDs or technical parameters. Claude
did not call a save tool. It said the start results did not expose the workflow
ID/token/revision and asked the user to provide a workflow ID or manually save.
Native evidence remained 613 live, 612 on disk, dirty, state `applied`.
This fails the required complete text workflow. No ID was supplied to turn this
into a false pass. The same card's Save font button was then used separately to
save the disposable result.

Evidence: `claude-before-text-save.json`, `claude-text-save-failed.json`.
The separate card cleanup save is verified by `claude-final-save-card.json`:
613 live/on disk, clean, `saved`.

Source inspection supports the observed gap: `edit_workflow_ui.py` supplies
human text in `content` and the control envelope only in `structuredContent`.
The card's `ui/update-model-context` also sends only `current.text`. The test
does not prove precisely where Claude omits the structured envelope, but does
prove the model cannot complete this interaction without additional identifiers.

## Cursor card sequence and UI findings

Started dirty: 710 live, 600 on disk. Cursor discovered the correct explicit
document and started +3 in apply mode. The text choices were visible directly;
the standard MCP App required expanding tool activity and the start tool result.
Inline Save As displayed its folder, filename, resolved path, and Back action.

The Save and continue button triggered Cursor's own permission dialog for
`respond_edit_workflow`. After approving that tool, the edit reached 713 live,
710 on disk, dirty, state `applied`. Its separate polling call to
`get_edit_workflow` also triggered a host permission dialog. These host dialogs
are not workflow reconfirmation prompts, but materially affect perceived speed.

During permission handling and revisiting the card, Cursor remounted its webview
with the original waiting-save snapshot even though the server was already
applied. Repeating the original Save and continue action reconciled to the
existing result; no second delta was applied. After approving the read call,
the card showed Applied in Glyphs · Not saved alongside a stale “The host did
not respond” error. A separate Save font action and read approval then showed
Saved; native verification confirms 713 live/on disk and clean.

Evidence: `cursor-before.json`, `cursor-after-save-continue.json`,
`cursor-final-save-card.json`. Cursor text fallback follow-up is recorded below.

Source inspection identifies related fixes to qualify: card requests have a
15-second timeout; a successful `refresh()` does not clear the displayed error;
initialization schedules polling only when the embedded snapshot has `poll`
true, so remounting an old waiting snapshot does not immediately reconcile.

### Cursor text follow-up and model quota

A second clean-font +1 request automatically reached 714 live, 713 on disk,
dirty and applied (`cursor-before-text-save.json`). Cursor tried to verify
through job/status reads, then displayed “You've hit your usage limit” with
Upgrade to Pro/Switch Models choices before the planned text save reply.
The model shown was Cursor Grok 4.6 Medium. No upgrade, purchase, or model
switch was made. Therefore the natural-language final save is **blocked**, not
reported as passed or as the same failure seen in Claude.

The retained shared card still worked without another model turn: expanded the
start result, approved its read call, clicked Save font, and approved the host's
tool/read prompts. The card showed Saved and native evidence confirmed 714
live/on disk, clean, state `saved` (`cursor-saved-after-quota.json`). Cleared the
test draft restored by Cursor's quota error to avoid an accidental repeat.

## Codex limitation

This task still exposes the original nine Glyphs tools even though installed
server status advertises all twelve. Tool discovery found no workflow tool or
connection refresh command. CUA refused access to `com.openai.codex` with
“Computer Use is not allowed to use the app 'com.openai.codex' for safety
reasons.” The restriction was not bypassed. A manual connector refresh was
requested; no response has been received at the time of this record.

Read-only status/native support is verified; new inline save behavior and
conversational workflow actions are **unverified**, not classified unsupported.
The Codex disposable fixture has not been opened or edited.

## Source preservation and limits

Both exercised disposable fonts were saved and closed through the tested UI.
The final native document list contains only Dactylotype, dirty false,
generation 0, current. Its source hash matches the pre-test baseline; Claude's
original file retains 610 after final Save As and the Codex fixture remains
untouched (`source-preservation.json`, `final-documents.json`). Native Glyphs
also created an autosave recovery copy of the Claude fixture during setup; it
was not treated as a prerequisite or final source save.

This retest covers the sequences described above, not every original plan case
in every client. Pathless fonts, successful manual-save resume, preview/discard,
restart, and unavailable UI are not newly claimed as client-level passes here.
Earlier automated/native evidence remains in the parent report. No product
code, installed runtime, release tag, or published artifact was changed during
this pass. Report whitespace verification passed.

## Required follow-up before release

- Preserve a compact machine-readable workflow reference and action envelope
  in model-visible tool content/context even when a host omits structured data.
  Requalify a new request followed by plain “Save and continue” and “Save the
  font” without ever providing IDs, tokens, or JSON to the user.
- Reconcile a mounted/reopened card to authoritative state before presenting
  actionable choices; clear superseded transport errors after a successful read.
  Exercise slow host permission approval and closed/reopened cards in Cursor.
- Report async progress accurately in assistant text; do not claim completion
  from a Preparing tool result.
- Remove the terminal empty-choice suffix, “You can also reply in the
  conversation: .”, observed in both clients (cosmetic).
- Complete the actual refreshed Codex host check. No release/tag/publication
  was performed during this retest.
