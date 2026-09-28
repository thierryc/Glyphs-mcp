# Milestone 8 resumption record

September 28, 2026. **Historical blocked-install handoff.**

The later user request authorizes consolidation, installation and local signing.
The installation blockage below is resolved; see the [combined candidate report](../beta8-release-candidate/README.md) for current evidence and remaining acceptance gates.
The original observations below are retained unchanged.

## Completed

- Tests-first exact typed `kerning_edit`, native preparation, guarded application, selective recovery and result presentation.
- Bounded read-only `kerning_proof`, with a pinned MIT-licensed dataset and 24 upstream language tags. No suggested values or automatic corrections.
- 329 focused regressions, 96 standalone native exact-edit cases, 60 fresh assignment benchmark runs and 20 fresh proof processes passed. See the milestone report and benchmark boundaries.
- Canonical guidance, routing fixtures and all 11 packaged skills synchronized; package checks retain twelve tools.
- Lean runtime rebuilt at the established `build/simple-native-scripting` target. Beta 8/build 50 retained. Runtime source matches the frozen candidate used for the final benchmarks.

No commit or publication has been performed. Existing milestone 1–7 changes remain uncommitted and must be preserved.

## Environment blockage

The MCP-only installer stopped progressing during `InstallationTransaction.__init__`, in a filesystem `mkdir` while copying the runtime into staging. At the last observation:

- Installer PID `93331` remained in `U` state after SIGKILL was requested. Do not assume it has exited; inspect fresh process state before resuming.
- Transaction: `~/Library/Application Support/Glyphs MCP/lean-v2/transaction-qyzb26du`. `backup/` was empty and `journal.json` absent. The installer had not reached service shutdown or live replacement.
- The installation and control locks remain held by that process. A retry refused with `Another installation is already running`. Do not remove/bypass those locks.
- The installation receipt was unchanged. The old sidecar still answered the actual Codex connector; Glyphs had been quit, so the bridge was unavailable.
- The independent desktop build stalled in `clang-stat-cache`, PID `91881`, also `U` after termination was requested. Its parent was terminated. No new desktop app was verified or installed.
- Disk space was sufficient. The underlying cause of these kernel waits was not established. Samples are retained in ignored `build/beta8-milestone8/`.
- CUA then reported that the Mac was locked and could not be unlocked automatically. Reopening Glyphs remains pending. Unlocking is required; if kernel waits persist, a user-managed macOS restart may be necessary. Do not reboot automatically.

The lean runtime build passed; desktop build and runtime installation did not. Do not treat their logs or receipt snapshots as successful completion.

## Identities

| Component | Built candidate | Still installed before the blocked replacement |
| --- | --- | --- |
| Bridge | `sha256:c853dee2cd1bbf400ab03ba06ff2312a9bffd9b820aea92835593ee79421a1c7` | `sha256:c35ab0983487fb32734006b1244a83d00264f0af24ae5b7395ec77653174364c` |
| Sidecar | `sha256:40e3344a89687224d514fb34d38df6018c60c9e38710efe74064d51b48326752` | `sha256:bb5297f858c9b66a541d159c2554cafb98c1dff1c92199e56bad09b7883722df` |

The last reachable sidecar reported the installed hash above. There is no loaded-candidate bridge evidence. Recheck all identities after any restart. Existing port 9680, auto-start, companion installations and Glyphs 4 settings must be preserved.

## Restore the user's session

Before the authorized quit, `before-install.json` recorded five saved, clean documents with no active operations. Reopen missing documents through native UI after unlocking; resolve fresh MCP bindings. Do not save or edit the original Dactylotype.

1. `/Users/thierryc/Documents/fonts/Dactylotype/Dactylotype.glyphspackage` — original and previously current.
2. `build/beta8-milestone5/editor/Conversation.glyphspackage`.
3. `build/beta8-milestone3/editor/Cleanup.glyphspackage`.
4. `build/beta8-milestone6/editor/glyphspackage/Checkpoint.glyphspackage`.
5. `build/beta8-milestone6/editor/glyphs/Checkpoint.glyphs`.

Relative paths in this record are rooted at `/Users/thierryc/Dev/github/thierryc/Glyphs-mcp-worktrees/v2`.

## Resume qualification

1. Inspect current processes and installer transaction state. If the stuck process has exited, use the established installer recovery/locking path. Do not manually replace live files or replay an uncertain edit.
2. Finish the existing MCP-only installation using `scripts/install_simple_v2.py --build build/simple-native-scripting --glyphs-app '/Applications/Glyphs 4.app' --only mcp --start`, after reconciling operations and accounting for any newly opened/dirty documents. Existing installation/relaunch authorization applies. Preserve companions. Runtime input links under `build/beta8-milestone1/runtime-inputs` point inside the old `/Applications/Glyphs MCP.app`; do not move that app while a builder uses them.
3. Finish `scripts/build_local_app.py` and verify its build receipt before any desktop app replacement. The prior attempt has no verified output. Follow the established installation procedure; do not edit installed plugin caches.
4. Reopen Glyphs, restore the prior session and verify built/installed/loaded hashes plus `kerning.edit.exact.v1` and `kerning.proof.v1`. M8 mutations require the candidate, not the still-installed M7 runtime.
5. Open the already-created disposable fixtures in `build/beta8-milestone8/editor/{glyphs,glyphspackage}/Kerning.{glyphs,glyphspackage}`. Each directory's `fixture.json` supplies exact masters. Do not regenerate or overwrite fixtures blindly.
6. Run `scripts/qualify_kerning_editor.py --format glyphs --output reports/beta8-milestone8/editor-glyphs.json`, then the corresponding `glyphspackage` command. The harness is prepared but unrun. It exercises 36 editor cases per format, selective recovery, actual Save, Keep → next task, duplicate actions and HTTP reconnects. It records state incrementally and refuses an existing output; inspect/reconcile any partial record before retrying.
7. Qualify actual editor native Undo/Redo for glyph-owned and group-only/document-owned history, verifying exact values and unrelated controls. Standalone native Undo tests do not satisfy this editor gate.
8. Exercise exact-edit preview/apply, Keep/Save and proof reads through the installed Codex connector. Record client latency separately from direct FastMCP HTTP and native-loop benchmarks. Existing card rendering checks from milestone 5 do not prove the new pair presentation. Use manual observation only for Codex UI; CUA access to Codex was denied previously.
9. Record authoritative installed/loaded evidence and editor/client outcomes. If fixing source, rerun affected checks and rebuild before claiming matching runtime qualification. Mark M8 complete only when all native/editor/client gates pass, then stop. No commit or publication is part of this milestone.

Runtime benchmarks need not be repeated merely because installation was blocked; repeat affected cases if production code changes.
