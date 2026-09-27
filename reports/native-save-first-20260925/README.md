# Save-first native scripting — September 25, 2026

Implemented in the v2 worktree and built as `build/python-scripts-save-first`.
The installed runtime remains unchanged. This extends the existing twelve tools;
there is no new generic tool or third execution engine.

## Behavior

- `executionMode="unrestricted", recovery="saved_file"` is capability-gated by
  `script.saved-file.v1`. No external worker or layer snapshots are needed.
- Live review resolves the exact manifest and checks syntax without executing
  Python. A dirty saved document can be reviewed. New documents use Save As first.
- **Save and run** explicitly authorizes the entire-font prerequisite save and
  the exact reviewed script. Native saving rechecks the review generation; a
  verified saved/clean baseline precedes execution. Changed reviews invalidate
  the action. Uncertain saves and reconnects never automatically execute Python.
- Callbacks run on the main thread in batches of up to 50, with a 10 ms scheduling
  budget. An individual callback or final native cleanup can exceed that budget.
  Whole scripts remain one invocation. Cancellation stops remaining callbacks.
- The wrapper retains document/target identity checks and protects fractional
  coordinates. It keeps partial and completed results visibly unsaved. Native
  Undo is not promised on this route. Output and errors remain bounded.
- **Keep changes without saving** releases the job. **Restore saved version**
  explicitly reloads the unchanged saved baseline using Glyphs' native font
  loader into the same document. This replaces the whole font, including later
  manual edits. A restored font gets a fresh MCP binding, returned to the client.
- A changed saved file disables restoration to that baseline; the user can use an
  earlier app version. No automatic backup is created. External effects and
  external image bytes are not restored. No crash-recovery guarantee is added.
- Saved backgrounds omit their transient layer IDs. The existing selected-layer
  adapter now normalizes those IDs against owning foreground identities and can
  qualify absent-ID snapshots. This prevents false saved/live conflicts when
  applying scoped edits to newly created backgrounds.

All actions and warnings have equivalent card and text representations. Saving
results remains explicit. Scoped/default execution and native declared-target
recovery remain available. Typed native actions stay closed.

## Recommendation: 250 surfaces

The initial 500-surface proposal was lowered to **250**: the measured scoped
workflow already took 6.78 s at 250 simple backgrounds, versus 0.58 s with the
save-first native route. The threshold is advisory, never an automatic mode or
recovery switch. Native execution is available below it. One surface is one
foreground/background layer, not one path or node.

Complexity matters: 100 backgrounds with 12 contours each took 15.89 s scoped.
The count policy does not claim to estimate runtime from node complexity. Skills
instruct clients to recommend native earlier for complex layers and preserve
scoped execution when selective recovery or scope validation is important.

## Measurements

Times below are seconds. These are single runs in fresh isolated Glyphs 4.1
(4107) processes for each fixture; each process measures the three modes in
sequence. Smaller timings vary with the workflow's polling cadence. This is
not an otherwise-idle-machine statistical study.

| Surfaces | Contours each | Direct callback | Save + native | Scoped | Native + layer recovery |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 1 | 0.010 | 0.59 | 3.35 | 2.58 |
| 250 | 1 | 0.025 | 0.58 | 6.78 | 4.94 |
| 500 | 1 | 0.047 | 0.83 | 12.03 | 8.97 |
| 1,000 | 1 | 0.095 | 0.97 | 22.24 | 17.14 |
| 4,096 | 1 | 0.421 | 2.65 | 88.89 | 94.96 |
| 100 | 12 | 0.093 | 0.59 | 15.89 | 7.48 |
| 500 | 12 | 0.464 | 1.16 | 74.61 | 32.68 |

The complete backend timings include saving, file hashes, job and chat actions,
review, the external worker's startup where applicable, application/execution,
native run-loop turns and completion polling. Human think time, HTTP/MCP/client
latency and the outer benchmark process launch are excluded. Restoration is
measured separately. There are no per-path model requests.

**Save qualification limit:** standalone `glyphs run` exposes a GSDocument stub
without Cocoa `dataOfType:error:` saving. A direct test failed closed and did not
execute Python. The benchmark harness therefore uses the real native GSFont
writer for disposable saves while retaining the production save service,
fingerprints and receipts. These are native-writer backend timings, not normal
editor NSDocument-save or installed chat-client timings. Production still uses
its existing NSDocument save adapter; no fallback writer was added to production.

The direct callback column excludes review, saving and recovery. It uses
native document-backed layers with rounding protection and Undo registration
disabled during measurement; it should not be compared directly with the earlier
bare-font kernel fixture. At 1,000 simple targets, the measured save-first backend
was about 23× faster than scoped, not a promise of 38× end-to-end client speed.
Native execution with full layer recovery was not always faster than scoped.

| Surfaces | Contours each | Peak process RSS (MiB, all modes) | Native restore (s) | Longest native scheduled chunk (ms) |
| ---: | ---: | ---: | ---: | ---: |
| 100 | 1 | 198.0 | 0.009 | 19.4 |
| 250 | 1 | 247.6 | 0.007 | 47.9 |
| 500 | 1 | 337.4 | 0.014 | 96.7 |
| 1,000 | 1 | 546.5 | 0.019 | 188.3 |
| 4,096 | 1 | 2386.8 | 0.068 | 770.5 |
| 100 | 12 | 332.2 | 0.008 | 19.8 |
| 500 | 12 | 1002.4 | 0.016 | 95.7 |

Peak RSS includes all modes, loaded/reloaded fixture fonts and native histories;
it does not isolate the fast route and is not the encoded recovery-state budget.
The native fast route retains zero layer recovery states. Longest scheduled
chunks include final cleanup: the largest simple fixture reached 771 ms despite
the per-batch budget. No visual frame-rate or full GUI responsiveness measurement
was performed. Raw JSON files retain stage timings, methodology and source
hashes. The final recommendation/text, restoration reconciliation and transient
background-ID normalization were finalized after the timing runs; their native
qualification is recorded separately in candidate artifacts.

## Verification and handoff

The full regression run passed **2,203 tests**, with two existing skips and two
sandbox socket tests deselected. Those two socket tests passed separately with
local socket access. Final focused checks passed **69 tests**. Native candidate
qualification covers the original scoped/recovery suites plus saved-file
execution/restoration in both `.glyphs` and `.glyphspackage`, whole scripts,
fractional geometry, preserved foregrounds, partial failures, cancellation,
later edits, source overwrites, and refreshed document bindings.

Card/text host tests cover Save and run, restoration choices, safe rendering,
no automatic execution, stale actions and reconnects. All 11 managed skills
synchronize; package checks preserve twelve tools and both runtime architectures.
The built candidate's imported module paths and code hashes are recorded with
its manifest. Normal editor NSDocument-save integration, actual installed-client
UI, and a runtime update remain unperformed in this pass. The current installation
is copied rather than development-linked, and was not replaced or restarted.

Use [the scripting contract](../../skills/glyphs/references/python-scripts.md)
and the existing [vertical flip callback](../../skills/glyphs-mcp-scripting/examples/vertical_flip.py).
Changes remain unstaged and uncommitted. Local routing and `.codex-local/` remain
untracked and excluded from distribution.
