# Automatic Keep countdown — September 26, 2026

Implemented and built; **not installed yet**. The running sidecar remains the previous candidate. Dactylotype has unsaved edits, so the established installer cannot close Glyphs safely without the user's saving/closing decision. No live font was saved, closed or modified during this feature pass.

New native-script workflows default to `auto_keep=true`. A visible connected card shows a 30-second progress bar after successful execution, then dispatches **Keep changes without saving** once. This ends the workflow's restoration offer, without saving, rerunning Python or asserting verified results.

**Wait for my answer** stops the countdown and persists the disabled setting for that workflow. Agents set top-level `auto_keep=false` for new workflows and carry an explicit opt-out into later requests until the user changes it. Text-only clients remain manual. Older persisted workflows are not retroactively opted in. Failed, cancelled and unknown outcomes stay manual.

The countdown stops while the card is hidden, disconnected, busy, or showing Script details. Returning begins a fresh countdown after a read. Before dispatch the card checks the workflow again and requires the same workflow ID, job ID, request fingerprint and revision. Concurrent disable/completion invalidates the old token. Duplicate requests cannot repeat effects. A lost response is reconciled without automatically retrying Keep. Card timeout dispatches carry `automatic=true`; the server restricts this to successful Keep and records `responseOrigin=card_timeout`. This is origin evidence, not human authentication. No timed Run, Save or Restore was added.

Validation:

- Full Python suite: **2,236 passed, two skipped, two socket cases deselected**, five existing dependency deprecation warnings. The socket tests are unchanged and passed in the preceding milestone; they were not counted again here.
- Final focused lifecycle/card suite: **37 passed**, after the final concurrent-state guard, Wait button checks and completed-state wording correction.
- Deterministic host tests execute the actual bundled card JavaScript: 30-second boundary, progress values, opt-out button and conversational disable, hidden cards, open details, stale identity, unsupported hosts, teardown, and lost-response no-replay behavior.
- Python regressions cover automatic Keep idempotency, no saves/reruns, explicit opt-out, restart persistence, stale cards and manual legacy/partial outcomes.
- Eleven canonical skills and packaged mirrors synchronized; package check still reports twelve tools and both runtime architectures. `git diff --check` passed.
- The local file URL for visual preview was blocked by Browser use security policy. No alternate route was attempted. Actual browser rendering and installed-card countdown are not claimed verified.

The initial isolated UI-test invocation lacked the repository PYTHONPATH; rerunning with `src/sidecar:src/protocol:src/bridge` passed. The first new restart test assigned a read-only service property; the test fixture was corrected to reset its backing coordinator. Neither was a product runtime failure.

[Build identity](build-identity.json), [full regression log](regressions.log), [final focused log](focused.log). The bridge fingerprint is unchanged; only the sidecar UI/workflow payload changed. Existing original-font edits and installed plugin caches were left untouched. No commit or publication.
