# Milestone 5 — conversation overhead

**Complete locally, September 28, 2026.** Implementation began September 27;
the installed card gate is now qualified with user-observed Codex interactions
and matching server evidence. Computer Use remains blocked from `com.openai.codex`;
no restriction was bypassed. See the [final qualification](#final-qualification--september-28)
for evidence, limits and cleanup. Earlier pending-gate notes below are chronological
records, superseded by that final qualification. Milestone 8 is not started.

## Changes

- Redelivered compact notifications for the same verified workflow, document,
  job, request fingerprint and revision no longer trigger another read.
- Closing/reopening Script details reuses matching loaded source/parameters.
  Completion still refreshes open details, and visibility/reconnection still
  reconciles server state. Explicit empty evidence replaces cached values.
- Document binding changes clear cached source/output. Late reads and mutation
  responses cannot replace a newer workflow in the card; reconciliation follows
  the current identity without replaying code or another action.
- Typed results expose their existing prepared summary in both card and text.
  A waiting request does not borrow its earlier blocking job's summary.
- Shared guidance gives a minimal call sequence. Fully explicit path targets
  use exact geometry/guards without unrelated context/selection reads. Selection
  reads remain required to resolve selection-dependent targets. Canonical skills,
  routing fixtures, tool descriptions and the packaged mirror were updated.

Twelve tools, task/save authorization, bounded reads, typed selective recovery,
script baseline restoration and the existing successful-result countdown remain.
Run, Save and Restore retain authoritative server checks. This milestone changes
conversation traffic and presentation; it does not change native edit algorithms.

## Tests first and regression results

- [Initial reproductions](tests-before.txt): six expected failures and two passing
  controls, before production edits. A frozen original card is retained under
  `build/beta8-milestone5/baseline/` for the paired measurements.
- [Routing failures](routing-before.txt) were recorded before changing the
  mandatory-selection guidance. [Routing result](routing-after.txt): 24 passed.
- [Lifecycle/script/UI checks](tests-focused.txt): 84 passed. These include
  previews, action authorization, save separation, stale tokens, duplicate
  actions, uncertain results, recovery and both Keep timers.
- [Full suite](tests-full.txt): **2,348 passed, two skipped, five existing
  warnings**, 109.10 seconds. No new skipped test.
- A subsequent blocking-summary reproduction failed before its one-line guard
  was added: [failure](summary-blocker-before.txt). The final conversation/UI
  run, including that guard and the late-mutation-response case, passed
  **12 tests**: [final focused result](tests-conversation-final.txt).
- Eleven-skill synchronization, twelve-tool package checks and diff whitespace
  checks pass. Local routing customizations and plugin caches remain untouched.

## Paired card measurements

These execute the actual bundled JavaScript in the deterministic test host.
They measure calls and JSON data volume, not rendered Codex behavior or network
latency. Both versions use the same script and interaction sequence.

| Interaction | Before | After |
| --- | ---: | ---: |
| Initial compact result plus ten identical redeliveries | 11 reads | 1 read |
| Open/close the same Script details five times | 5 full reads | 1 full read |
| Total reads for that details sequence | 6 | 2 |
| JSON data bytes for that details sequence | 134,383 | 27,419 |
| Mutating calls in either sequence | 0 | 0 |

The byte fixture contains 700 comment lines of literal text: the 79.6% reduction
is specific to repeatedly opening those details. It is not an overall edit-speed
claim. Evidence: [duplicate before](card-duplicate-before.json),
[duplicate after](card-duplicate-after.json), [details before](card-details-before.json),
[details after](card-details-after.json).

## Actual Glyphs and installed Codex tasks

The installed Codex MCP connection edited a disposable saved copy of the real
Dactylotype package at `build/beta8-milestone5/editor/Conversation.glyphspackage`.
The original font was neither edited nor saved. Its bytes match the pre-test
hash, and its original window was reopened after the authorized relaunch.

1. **Typed path:** move Regular `o`, path 0, node 0 by +0.25/−0.5. The exact
   fractional result, other 11 nodes and 53 foreground-layer controls passed.
   Selective recovery restored the exact path, including absent names. An
   authorized editor Save completed before the next task.
2. **Explicit spacing:** native callbacks translated Regular H/n/o contents by
   12.5 and increased advances by 20.75. All three widths, H/n fractional bounds,
   all 12 nodes of o's first path and 51 foreground-layer controls passed.
   Exact details and compact omission were checked. Saved-version restoration
   produced a fresh binding and restored all 54 checked layers.
3. **Exact kerning:** a whole script set LTR A/V to −60.25 and T/o to −45.5.
   Fresh stored-value reads verified both assignments, 25 pair/master controls
   and 54 layer controls. Output details loaded. Restoration recovered all 27
   sampled kerning values and returned another fresh binding.

There were two qualification problems, preserved in the evidence:

- Glyphs returned whole-number layer bounds for `o` before and after spacing;
  the first fractional-bounds assertion failed. The exact path-node read verified
  the shift. This does not qualify fractional bearings from that bounds field,
  nor establish complete geometry verification for every H/n/o contour/component.
  Investigating native bounds precision is a separate follow-up.
- The initial kerning test used the nonexistent Glyphs 4 import `LTR`. Module
  initialization failed before assignments. Its original workflow was restored;
  a revised request used `GSLTR`, verified in the installed wrapper source. No
  uncertain code was replayed. This was an error in the qualification script.

### Installed timings

One actual task per route; **not a five-run performance benchmark**. Calls include
verification, explicit Wait opt-out, optional details and recovery. End-to-end
wall time spans agent turns and, for spacing, the measurement investigation.
The failed kerning attempt is reported separately, not hidden in the successful run.

| Successful task | Calls | Re-encoded MCP result bytes | Sum of tool-call time | Task wall time |
| --- | ---: | ---: | ---: | ---: |
| Typed path, recovery and Save | 18 | 137,934 | 37.90 s | 87.63 s |
| H/n/o spacing and restoration | 14 | 130,827 | 25.03 s | 115.92 s |
| Corrected kerning and restoration | 12 | 101,596 | 29.96 s | 69.07 s |

Setup was three calls, 7.37 seconds and 14,872 bytes, once for the connection,
document and masters. No per-task status/document rediscovery occurred.
The unsuccessful kerning attempt and restoration added nine calls, 10.99 seconds
of tool time and 56,545 bytes. Reported bytes include structured and text
representations re-encoded as compact UTF-8 JSON; they are not network wire size.

Path start-to-applied was 1.84 seconds. Spacing preparation was 0.88 seconds and
Run-to-applied 4.35 seconds; corrected kerning preparation, including its baseline
read, was 3.64 seconds and Run-to-applied 3.96 seconds. These include connector
and polling latency. Native execution CPU time was not isolated; earlier direct
loop measurements must not be compared as if they had this methodology.

Raw evidence: [installed calls/results](installed-tasks.json),
[aggregated metrics](installed-metrics.json). The UI card cache optimizations do
not speed up this text-only verification sequence; their measured benefit is
the reduced repeated card traffic above. No new capacity or responsiveness
guarantee is made.

## Build, installation and remaining gate

The established `build/simple-native-scripting` target was rebuilt and installed
with `--only mcp --start` after checking the clean open documents. Existing
inspector identities and the private runtime were preserved. Source, built and
installed contents match for all 58 sidecar/protocol Python and HTML files.
The installed endpoint serves the exact source card resource, confirmed with a
fresh local FastMCP read; that check is not a rendered-card test.

- Sidecar: `sha256:151e72c99245b385af616dba0c9d9424558ac92ca5ec2393818bafa8c1a59b80`
- Bridge: `sha256:d9ad46e01f0f0a5baa93320dc6e9d887d8b4b5485f6a89950015d238d7273119`
- Loaded: Beta 8/build 50, Glyphs 4.1 (4107), twelve tools, `script.native.v1`.
- [Build](build.json), [MCP-only installation](install.json),
  [identity verification](identity-verification.json), [served card](served-card.json).

**Still required:** a real Codex card check of repeated Script details,
completion details, countdown, immediate Wait, hidden/disconnected behavior and
reconciliation. Simulated-host coverage passes but does not close this gate.
No commit, publication, plugin-cache edit or milestone 6 implementation occurred.

## September 28 follow-up — manual visual qualification in progress

Retested against the milestone-7 installed candidate (sidecar `bb5297f858c9`,
bridge `c35ab0983487`). Computer Use still explicitly refuses access to
`com.openai.codex`; no alternate access method was used to bypass that restriction.

The user confirmed **“Card visible; details work”** after opening, closing and
reopening Script details twice in the actual Codex card. This is user-observed
visual evidence. It is recorded separately from automated server checks in
[visual-followup.json](visual-followup.json).

The installed HTML matches source and its deterministic-host checks pass:
[served-card check](current-served-card-check.json). Current focused regressions
pass **47 tests**: [results](current-card-regressions.txt). These tests do not
substitute for the remaining visual observations.

The actual card ran a print-only script on the disposable
`Conversation.glyphspackage`: workflow `edit_7d6e4f20165e4cc38ae37abda7d1dcfd`,
job `job_6de0d49779554f29b23e662737676a9a`. The user confirmed **“Output correct;
bar appeared; Wait stopped Keep”**. This supports automatic completion-detail
refresh, literal `<b>` rendering, and the observed local timer pause.

Authoritative server reads then showed `applied` at revision 13 and `saved` at
revision 21, with a verified native Save and unchanged source hash. The stored
record consumed exactly Run (revision 5) and Save (revision 13); **no Wait action
was consumed**, and `autoKeepEnabled` remained true. Thus this observation does
not yet qualify persisted opt-out or reconnection. Clarification was requested;
the evidence is retained in [visual-wait-server.json](visual-wait-server.json)
and [visual-action-evidence.json](visual-action-evidence.json). The agent did not
dispatch Run, Save or Keep during these card checks.

Visible automatic Keep and hidden/disconnected/reconnection checks also remain.
The milestone is **not yet complete**. No source change or rebuild was needed
for this follow-up. The first workflow is now settled by its verified Save.

### Follow-up: automatic Keep observed; isolated Wait check pending

The second print-only workflow, `edit_c64c3ae948e14ea6b7c468cf114b79e6`,
finished via **automatic Keep**: revision 17, `responseOrigin: card_timeout`,
with a consumed `finish_script` action carrying `automatic=true`. The user
also pasted that final result. This verifies a real installed-card automatic
completion. It does not qualify Wait: although the user reported “Wait worked;
Keep still offered,” this workflow consumed Run and timed Keep, with no accepted
Wait. The conflicting observations remain recorded, without attributing a cause.
See [server evidence](visual-wait-retest.json) and
[manual observations](visual-followup.json).

The disposable font was then saved under the existing test-save authorization.
The native Save succeeded and its source hash stayed unchanged
(`sha256:3c64b127d785fabd7ea381769f04944da237f2440c6d5cfabebbfb41077c492f`).
No original Dactylotype document was saved.

An isolated single-card preview is now waiting: workflow
`edit_bc03ecc881a3484295751558fa908e22`, job
`job_6d260d4e530949ec89f3bee5232b5831`. The user was asked to click the card's
Wait button **before Run**, removing the countdown race. Server observation at
revision 6 is still `waiting_run`, automatic Keep enabled, no execution. Subsequent
reads use a local MCP client so they do not create a second visible card.
Persisted opt-out and hidden/disconnected-card reconciliation remain unqualified.
No implementation changes or rebuild were made from these inconclusive observations.

### Persisted Wait verified

The isolated card's Wait action succeeded: the MCP App returned revision 9,
`waiting_run`, with `autoKeep.enabled=false`; a fresh local MCP read confirmed
that state before execution. Under the existing diagnostic-test authorization,
the agent then dispatched Run once. The resulting revision 17 is `applied`, with
Keep, Save and Restore available and automatic Keep still disabled. Output is
exactly `Milestone 5 single-card check completed once.\n`.

[Full pre/post-run evidence](visual-single-card-run.json) records this separately
from the earlier inconclusive Wait observations. The user is checking a 35-second
hide/return and matching completion details. Actual transport disconnect/reconnect
is next; these checks remain pending until observed.

### Actual sidecar disconnection and reconciliation

The installed sidecar was stopped through its existing idle reservation guard,
then restarted after 42.09 seconds with unchanged settings. Glyphs and its five
open fonts stayed open; their document IDs, paths and dirty states were unchanged.
The runtime fingerprint remained `bb5297f858c9`. The retained result became
`interrupted`; an explicit Check result reconciled it back to `applied` without
Run, Save or Keep. Wait remained disabled. The native operation evidence and
script output matched exactly before and after. A fresh `get_edit_workflow` through
the installed Codex connector also succeeded.

[Raw connection evidence](visual-reconnect.json),
[identity and action checks](visual-reconnect-summary.json).
The only consumed actions on this test are Wait, Run and Check result. This is
transport/server evidence, not a claim that the disconnected card was visually
observed. The user requested a retry of the hide/return observation, which is
pending on the reconnected card. A separate enabled-timer hide test is also needed;
an opted-out result alone cannot establish hidden countdown behavior.

## Final qualification — September 28

**Milestone 5 is complete locally.** The user-assisted card checks close the
remaining gate on the already-built and installed milestone-7 runtime. No new
production-code change was needed. The earlier inconclusive Wait observations
are retained above; they were not counted as passes.

| Check | Evidence and outcome |
| --- | --- |
| Script details | User confirmed repeated opening/reopening and automatic completion output; literal `<b>` tags remained text. Matching source and output are retained in the server reads. |
| Visible automatic Keep | The actual card completed the second diagnostic workflow with `responseOrigin=card_timeout` and `automatic=true`; the user pasted its final result. |
| Persistent Wait | The isolated card consumed Wait before Run. The same workflow retained `autoKeep.enabled=false` through execution, transport loss and reconciliation. |
| Hidden result countdown and Wait | On the typed A-width card, the user reported “the hidden countdown work” after the requested hide/return test. The server still had the applied result and consumed Wait at revision 14, with no Keep or Save; revision 17 had automatic Keep disabled. |
| Real disconnect/reconnect | The managed sidecar was offline for 42.09 seconds. Check result reconciled the same job from interrupted to applied. Output, native-operation evidence and document bindings matched; Run and Save were not replayed. The installed Codex tool connection and subsequent card actions worked. |
| Typed edit and selective recovery | All nine stored A-layer widths increased exactly 0.125. Their outline hashes/metrics keys and B Regular's width/hash/keys stayed unchanged. Selective Undo restored every recorded value. |
| Cleanup | Saving the restored disposable fixture reproduced its original saved-source hash. All five open fonts are clean, no active operations remain, and original Dactylotype was neither edited nor saved. |

The visual hide duration is user-observed, not an instrumented browser timing.
The disconnected error screen was not directly observed: the tested evidence is
actual transport loss, no replay, persisted opt-out, and working card actions
after reconnection. Deterministic-host tests separately cover failure rendering,
hidden/disconnected behavior, stale tokens, rejected Wait and both result timers.
Do not present those simulated checks as direct Codex visual observations.

Final evidence:

- [User observations and qualification matrix](visual-followup.json).
- [Persistent Wait and one Run](visual-single-card-run.json).
- [Real reconnect](visual-reconnect-summary.json), with [full records](visual-reconnect.json).
- [Typed baseline](visual-typed-before.json), [applied values](visual-typed-applied.json),
  [hidden/Wait result](visual-typed-hidden-result.json) and [selective recovery/save](visual-typed-cleanup.json).

The preview-read test initially expected `ready` but received `applied`: an
explicit card Apply had already arrived. The full nine-row report and fresh live
reads verified the intended scope and values; this timing assumption was not a
production failure and caused no reapplication.

The current focused regression run passes **47 tests**; the installed HTML matches
source and passes the deterministic host. The latest full runtime qualification
remains milestone 7's **2,414 passed, three skipped**; no production source changed
during this follow-up, so no new rebuild, installation or full-suite claim is made.
Loaded identities remain sidecar `bb5297f858c9`, bridge `c35ab0983487`, Beta 8/build 50.
No commit, publication or plugin-cache edit. Stop here before milestone 8 kerning.

Final documentation checks: **3 passed**; eleven skills synchronized; package
assertions retain twelve public tools and both runtime architectures; `git diff
--check` passes. [Completion receipt](completion.json). These checks are additional
to the recorded 47 focused regressions, not another full-suite run.
