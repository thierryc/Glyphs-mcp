# Follow-up review: performance, capacity and simplicity

Reviewed September 26, 2026. Source and prior qualification evidence were read;
focused reproductions used Python fixtures and the JavaScript mock host. No live
font was changed and no runtime was installed or restarted. The findings below
were not fixed during this review.

The one-route design is a substantial improvement over the scoped/native/snapshot
candidate. It is ready for a focused correction pass, not a claim of completed
native editor/client qualification. The passing regression count did not expose
several transitions between workflows or details/polling interactions.

## Findings

1. **A waiting task does not resume after Keep on an earlier script.**
   In `src/sidecar/glyphs_mcp_sidecar/edit_workflow.py:174`, blocker completion
   recognizes accepted, discarded and cancelled, but not the script's completed
   state. Reproduction: run script A, start B while A is applied, Keep A, then
   refresh B. A becomes executed/completed while B stays blocked_review. That
   screen also offers the typed-job "Undo earlier changes" action from
   `edit_workflow_state.py:155`; the bridge explicitly refuses script discard in
   `src/bridge/glyphs_mcp_bridge/core.py:281`. This is a user-visible workflow bug.
   Recognize completed scripts and use script-specific Keep/Save/Restore choices
   or direct the user to the original workflow. Do not give whole-font reload an
   ordinary Undo label.

2. **The bulk limit is checked before eligible backgrounds are resolved.**
   `src/protocol/glyphs_mcp_protocol/script_targets.py:17` expands every glyph and
   passes that list to `scripts.targets`, which applies the 4,096 limit before
   missing/empty backgrounds are skipped. A 4,097-glyph fixture with only one
   eligible background fails with "at most 4,096 surfaces". Count the resolved
   surfaces for a bulk selector, with bounded traversal/reporting, rather than
   treating all candidate glyphs as selected surfaces. Keep the explicit request
   size limit.

3. **Background eligibility assumes vector-like contents.**
   `script_targets.py:33` recognizes shapes, anchors, hints, guides and annotations
   only. An existing image-only background is classified as empty and omitted.
   This is too narrow for a generic scripting tool; an image adjustment callback
   never receives that target. Define eligibility separately from the vertical
   flip example and cover image/metadata content, without recreating snapshots.

4. **Compact updates erase output that Script details already loaded.**
   `src/sidecar/glyphs_mcp_sidecar/edit_workflow_v1.html:89` caches source/options,
   but line 131 renders output from the latest compact job. That job deliberately
   omits output. Mock-host reproduction: details show VISIBLE_OUTPUT; a same-request
   compact update retains source but removes VISIBLE_OUTPUT. Preserve loaded
   evidence for the matching request/job and refresh it once on completion when
   details are open. Keep ordinary polling compact.

5. **Finished-workflow reads still perform whole-source work.**
   `src/sidecar/glyphs_mcp_sidecar/saved_script.py:67` hashes the complete saved
   source on every result read while restoration is available. Ten unchanged
   reads caused ten full hashes in the focused reproduction. `source_identity.py`
   traverses and reads every package file. This is proportional to font/package
   size, not selected target count, and happens under the workflow lock. The bridge
   already verifies the full hash before restoration. Reuse recently checked
   presentation state and retain authoritative validation at Run/Restore; choose
   a small invalidation strategy rather than a new general cache subsystem.

6. **Preparation readiness waits for a periodic workflow tick.**
   `edit_workflow.py:36` advances preparation every 250 ms; `get` at line 116 does
   not advance preparing workflows. In an isolated fixture the job was ready at
   0.0081 s, an immediate workflow read still said preparing, and waiting_run was
   visible at 0.2778 s. This helps explain the approximately 0.31 s preparation
   floor in the benchmark. Expose finished preparation promptly through the
   existing workflow, without changing authorization or executing on reads.

These are bounded correctness/performance fixes. Reintroducing scoped execution,
script snapshots, staging or another route-selection threshold would not address
them.

## What the performance evidence supports

| Fixture | Direct callback median | Native workflow median | Additional measured time |
| --- | ---: | ---: | ---: |
| 100 simple backgrounds | 0.009 s | 0.577 s | 0.568 s |
| 1,000 simple backgrounds | 0.097 s | 0.843 s | 0.746 s |
| 4,096 simple backgrounds | 0.386 s | 1.681 s | 1.296 s |
| 100 backgrounds, 12 contours each | 0.100 s | 0.576 s | 0.476 s |
| 500 backgrounds, 12 contours each | 0.515 s | 1.109 s | 0.594 s |

Five fresh processes per fixture and mode are a useful improvement in measurement
discipline. The wrapper remains noticeably slower than a tight native loop, but
absolute latency is reasonable for these bulk tasks. At 4,096 surfaces the native
workflow is about 4.4 times the direct callback duration; at 1,000 it is about
8.6 times. These are not apples-to-apples engine overhead ratios: the workflow
includes validation, an authorized fixture save and polling; direct timing
excludes setup/cleanup. Do not compare the old 0.48 s direct figure with the new
0.097 s figure as if they were identical experiments.

The longest measured scheduled chunk was 19.32 ms and isolated native peak RSS
at 4,096 had a 321.7 MiB median. Those are useful observations, not a responsiveness
or memory guarantee. Review/target resolution, disk hashing, actual editor saving,
reload and chat transport are not all covered by that chunk timer. The card polls
at 1.5-second intervals; the benchmark polls at 10 ms. Visible client latency will
therefore differ.

The fixtures use three-node triangles, including the 12-contour fixtures. They
exercise repetition and batching well, but do not qualify large curved outlines,
component-heavy fonts, large image assets, expensive callbacks, or large package
I/O. The 4,096 limit is a manifest bound, not a guarantee for all fonts of that
size. Whole scripts with targets:[] can traverse more objects; no claim of bounded
Python CPU or memory follows from the manifest limit.

## What was done well

- One execution capability and one script recovery contract remove route
  selection, serialization and snapshot complexity from custom edits.
- A clean saved font needs no extra Save. Saving remains separately authorized,
  and uncertain saves do not become permission to run Python.
- Revision-bound actions and outcome reconciliation prevent ordinary retries
  from replaying code. Old scoped requests are rejected explicitly.
- Fractional-coordinate protection, incremental cleanup and local callback loops
  are retained without per-path tool calls.
- Successful execution, completed callbacks and verified results are kept
  distinct. Source inspection is optional for an authorized result task.
- Typed jobs retain their specialized algorithms and selective recovery. Skills
  and their packaged mirror describe the same public route; the tool count stays
  twelve.

## Simplicity and remaining qualification

Saved-version reload is the right default for this bulk-script route. It is not a
universal replacement for typed edits: it replaces all later unsaved work, cannot
restore an overwritten baseline or external effects, and does not provide selective
Undo. Keeping typed recovery avoids forcing that tradeoff onto small supported
edits.

The largest architectural mistake was promising complete selected-layer script
recovery before establishing whether its serialization and latency costs served
the bulk use case. The current cleanup fixes that direction. The remaining mistake
is partial adaptation of the shared conversation state machine: individual script
flows work better than transitions between tasks. Fix and test those transitions
before adding another abstraction.

Native editor NSDocument saving/restoration and an installed chat-client workflow
remain unqualified. The 60 native fixture checks use a real GSFont writer through
a fixture adapter, not actual editor Save. The 2,208 regression passes plus two
socket tests remain valid evidence from the previous run, but do not negate the
newly reproduced findings above. Prioritize the six focused fixes, then the pending
editor/client gate and a representative complex-font measurement. No higher
target limit or additional script mode is justified by this review.
