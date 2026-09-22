# Designer-friendly workflow wording

Implemented the approved wording pass on September 22, 2026. Historical
qualification reports are unchanged. This record covers source, built payload,
and browser-fixture verification; the installed MCP runtime was not replaced.

## Changes

- Shared server messages now supply the card heading and optional supporting
  explanation, avoiding a second, conflicting set of UI headings.
- Saved results say **Font saved.** once. Completed progress, empty action rows,
  and empty conversation-choice footers are hidden.
- Preview discard, applied undo, and outcome checks are labelled **Discard
  preview**, **Undo these changes**, and **Check result**. Earlier edits offer
  explicit save/undo choices.
- Technical evidence stays under **Details**. Warnings and useful next steps
  stay visible; text responses retain the underlying error explanation.
- Both preview disposal and successful reversal use **Changes discarded.**
  Failed recovery retains failure state and evidence, never a success message.
- Updated the conversation and first-session tutorials and shared skill guidance;
  synchronized the packaged skills. Restored the width mutation JSON example in
  the technical reference because the earlier conversation tutorial conversion
  had removed the only example covered by the documentation validation test.

The tool signatures, action identifiers/tokens, stored states, save authorization,
source validation, native Undo and guarded discard logic are unchanged. The
text-action envelope and stale-card fixes remain separate outstanding work.

## Verification

- Focused workflow, card, and documentation checks: **29 passed**.
- Standard-host fixture executes the actual bundled JavaScript with server-made
  messages for every defined workflow state, checking single headings, supporting
  text, hidden completed progress, empty footers, and retained error details.
- Existing guarded-discard regression additionally verifies that a later edit
  conflict does not produce a successful discard or undo confirmation.
- Documentation production build, lean package gate, synchronization of eleven
  skills, source-to-build byte comparison, and patch whitespace checks passed.
- Full Python suite: **2,148 passed, 2 skipped**; see `python-tests.log` and
  `python-tests.md`. The first sandboxed run found the missing width example and
  two blocked localhost socket tests. The example was restored; all 20 server
  control tests then passed with local socket access.

Visual inspection used the unmodified bundled card in a standard-message host
fixture inside Codex's in-app browser at `http://127.0.0.1:8769/`. The disposable
file is `build/workflow-wording-preview/Workflow Sample.glyphs`. Saved, applied,
preview and failure displays were inspected; the dark theme and renamed buttons
were checked. Saved shows one confirmation and Details. Preview shows one
change and Discard preview. Failed recovery shows a failure and a direction to
inspect Details, without a success confirmation.

This is browser-fixture visual evidence, not a new installed inline-MCP or native
font-mutation qualification. No user font was edited, saved, or closed. The user's
earlier screenshot established inline rendering of the previous candidate in
Codex; it does not establish that this updated candidate is installed.

## Candidate

`build/workflow-wording/manifest.json` identifies the assembled candidate.
Sidecar code hash: `sha256:6a8206d62c45aa2efa51246bb3f989370740bd7ca064b5e867fce84bd4d5929c`.
Bridge code hash remains `sha256:c288fa8ec5bfe426168297dc192da457692ce77e61fa56901c46a5db06b40ebb`.
No installation, release tag, or publication was performed.
