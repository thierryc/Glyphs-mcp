# Beta 8 milestone 3 — incremental native cleanup

Status: **complete locally. Implementation, 2,322 regressions (two skips), native
harness qualification, all 100 benchmark runs and installed/editor checks pass.**
The [actual editor report](editor-qualification.md) records saving/restoration,
Codex interaction, large cleanup, the discovered inventory cost and its fix.

At the earlier source handoff, the user requested continuation after adding milestone 7 to the plan. Source
work for milestone 3 proceeds without treating milestone 2's installed gate as
complete. No unrelated font was saved, closed or restarted; milestone 4 has not
started.

## Changes and scope

- Close owned native Undo groups in reverse order, one manager per cleanup step.
  Preserve each manager's original automatic-grouping setting and native history.
- Restore rounding flags and release cached layer/rollback references across
  scheduled chunks. Retain the existing time budget and batch bound.
- Keep the existing operation active and its mutation reservation held until
  cleanup finishes. Duplicate/reconnect reads retain that same operation; no
  early Keep, Save, replacement job or terminal success is allowed.
- Continue attempting remaining groups and flags after a cleanup failure. An
  exception from one rounding setter must not skip later targets.
- Script cleanup already restores target precision incrementally. Release its
  manager references alongside each target and reuse the final shared cleanup.
- If scheduling itself fails, drain cleanup synchronously and report failure.
  A missing scheduler cannot provide yielding. This exception, individual native
  calls and arbitrary script invocations have no maximum-pause guarantee.

No tool, execution mode, snapshot representation, recovery policy or limit is
added. Existing typed selective recovery and saved-version script restoration
remain distinct. Cancellation after all typed writes have finished does not
interrupt mandatory cleanup; the result can still be applied and offer selective
Undo afterward.

## Tests-first evidence

- [Initial regressions](tests-before.txt): seven failures against the frozen
  milestone 2 runtime, exposing unbounded cleanup and whole-manager copying.
- [Rounding exception regression](tests-rounding-exception-before.txt): one
  additional failure before making flag restoration continue after an exception.
- Focused tests cover success, cancellation, target conflicts, cleanup failures,
  elapsed budget and batch bounds, duplicate reads/actions, retained ownership,
  native history, selective recovery and script execution without replay.
- The first full suite found the existing source-size assertion and two
  sandbox-denied local listeners. Cleanup helpers were extracted without raising
  budgets. The two listener tests passed with localhost access. Final results
  are recorded separately; earlier failed evidence is retained.
- [Final suite](tests-final.txt): **2,320 passed, two skipped**, with the existing
  dependency deprecation warnings. [Focused checks](tests-focused-final.txt):
  89 passed. The skips are unavailable Copilot CLI and the opt-in dependency
  installation matrix; they are not counted as native qualification.
- Native cleanup tests in [.glyphs](native-glyphs-final.json) and
  [.glyphspackage](native-glyphspackage-final.json) pass success, cancellation and
  target-conflict rollback. Exact fractional widths, untouched controls, original
  rounding/grouping settings, native Undo/Redo and selective recovery are checked.
  The initial [failed probe](native-glyphs.json) and [diagnostic](native-glyphs-diagnostic.json)
  are preserved: the harness assumed insertion order, but Glyphs reordered the
  glyphs. The corrected verifier compares exact glyph names, retaining all value
  and control assertions. No production-code change was required for that failure.
- Retained typed qualification passes in [.glyphs](retained-typed-glyphs.json)
  and [.glyphspackage](retained-typed-glyphspackage.json), covering two masters,
  foreground/background outlines, components, metadata, nullable node names,
  color labels, native Undo/Redo and selective recovery. Retained script capacity,
  cancellation and saved-version recovery checks also pass in
  [.glyphs](retained-script-glyphs.json) and [.glyphspackage](retained-script-glyphspackage.json).

## Native performance methodology

The [frozen source identity](baseline-identity.json) is the milestone 2 working
runtime, not clean HEAD or v1. Existing M1/M2 benchmark scripts and immutable
fixtures are reused with the same instrumentation on both routes. Five fresh
native processes per route/format cover width edits at 1,000/4,096 layers and
simple-background scripts at 1,000/10,000/20,000 targets.

All **100 runs pass**. The [comparison table](matrix/README.md) and
[complete stage statistics](matrix/summary.json) report medians and ranges.
Selected medians in seconds:

| Width targets | Format | Preparation + application/polling before → after | Longest scheduled cleanup before → after |
| ---: | --- | ---: | ---: |
| 1,000 | `.glyphs` | 0.658 → 0.900 | 0.215 → 0.010 |
| 1,000 | `.glyphspackage` | 1.254 → 1.630 | 0.233 → 0.010 |
| 4,096 | `.glyphs` | 2.596 → 3.032 | 0.933 → 0.011 |
| 4,096 | `.glyphspackage` | 2.999 → 3.623 | 0.856 → 0.011 |

**This improves typed cleanup responsiveness at a throughput cost.** Edit
elapsed time increases about 17–37% in these cases; selective recovery also
takes longer. At 1,000 `.glyphs` widths, median measured native cleanup work
including recovery is nearly unchanged (0.422 → 0.435 seconds), while scheduled
cleanup turns increase from 2 to 124. Yielding and the existing polling cadence
add elapsed time. The implementation retains the existing batch/time budgets
rather than promising equal total time or concealing the regression.

Script times remain broadly similar: at 20,000 backgrounds `.glyphs` changes
from 7.851 to 8.163 seconds and packages from 15.756 to 15.238 seconds, with
overlapping run ranges. Scripts already released target rounding incrementally.
The maximum isolated process RSS across the matrix is effectively unchanged,
724.1 → 723.3 MiB. The longest scheduled work across **all** stages is still
1.280 → 1.251 seconds, principally outside typed cleanup. No overall 10 ms
responsiveness guarantee is implied; even candidate cleanup has measured
outliers above the scheduling budget (maximum 22.4 ms in this matrix).

Timings separate preparation, application/execution and polling, verification,
selective recovery or whole-font restoration. Adapter cleanup instrumentation
includes application and selective recovery where present. A baseline step is
its synchronous final cleanup; a candidate step is one generator advance.
Scheduled cleanup maxima include other work in the same callback. Peak RSS
includes the native runtime, loaded fixture and verification. CLI startup and
fixture setup are excluded from edit timing. Source checks/build activity and
ordinary desktop activity can overlap; no exclusive CPU reservation is claimed.

Standalone native documents verify behavior and serialization; they do not
exercise actual editor Save, open-document interaction or installed-client
latency. Those separate gates are now recorded in the actual editor report. The unchanged saved/clean benchmark
fixtures require zero saves; this milestone changes no save implementation.

## Original installation boundary (superseded by editor qualification)

The candidate is rebuilt into the established `build/simple-native-scripting`
target. [Source/build identity](candidate-identity.json), [manifest](build.json)
and [byte verification](build-verification.json) record 133 matching Python
source/built copies. [Package checks](package-check.txt) retain twelve tools,
eleven synchronized skills and both runtime architectures. Runtime installation
has not been updated.

The existing installation/relaunch authorization remains available. Dactylotype
was rechecked after qualification through the installed MCP connection and
remains dirty; no MCP operations or jobs are active. The [installed boundary](installed-boundary.json)
records the still-loaded milestone 1 identities, distinct from this candidate. Its save
or close still needs the user's decision. Do not replace that decision with a
save, close, restart or mutation of the live font file. Reconcile jobs and verify
source, built, installed and loaded identities before later installed tests.

No commit, publication or milestone 4 work is included.
