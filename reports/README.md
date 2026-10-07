# Lean v2 qualification records

For the current stable release, see [V2 release qualification](../V2-RELEASE.md).
The reports below are historical snapshots. Beta guides and validation notes
removed from the current tree remain available in the
[v2.0.0 source tag](https://github.com/thierryc/Glyphs-mcp/tree/v2.0.0).

[Beta 11 release](beta11-release-candidate/README.md) records qualification of
the published release identity and build, inheriting Beta 10's runtime behavior.

[Beta 10 release](beta10-release-candidate/README.md) records the creation,
checkpoint and bundled-engine release checks.
[Font creation and installation](document-creation-20260930/README.md) records
live creation, duplicate reuse, save and native reopen in both source formats.

[Beta 8 milestone 7 — consolidation](beta8-milestone7/README.md) shortens the
catalog by 25.51% in description bytes, corrects current guidance and shares
export hashing. The final suite passes 2,414 tests; the rebuilt/installed runtime,
matching desktop app and a real Codex export are verified. No edit-speed or new
capacity claim is made. Milestone 8 has not started. Milestone 5’s later card
qualification closes the visual-card gap; signed-update qualification remains open.

[Beta 8 milestone 6 — Git checkpoints](beta8-milestone6/README.md) adds opt-in
font-only checkpoints, durable action evidence, history/comparison/restoration
and the Git-enabled project template. The installed MCP, native editor and
desktop app checks pass, with 2,404 Python tests, 214 desktop tests and 20 fresh
native-process controls. Actual editor Save/checkpoint medians were 1.99 seconds
for `.glyphs` and 2.56 seconds for `.glyphspackage`; package restoration dropped
to 2.88 seconds after bounded Git batching. Checkpointing adds latency; full
methodology and limits are disclosed. Its then-open milestone-5 card gate was
subsequently closed by the qualification below.

[Beta 8 milestone 5 — conversation overhead](beta8-milestone5/README.md)
reduces repeated card reads, binds cached details to the document and prevents
late responses replacing a newer workflow. It is rebuilt and installed, with
2,348 passing implementation regressions and installed path/spacing/kerning checks.
The final Codex card gate passed September 28 through user-observed Details,
literal output, countdown, hidden-card and Wait checks, matching server evidence,
and actual sidecar disconnect/reconnect. Current focused checks pass 47 tests.
The final typed test was selectively undone and saved with its original file hash.

[Beta 8 milestone 4 — active-work polling](beta8-milestone4/README.md)
replaces completed-history scans with volatile indexes and skips unchanged job
writes. Its 2,338 regressions (two skips), 80 final paired benchmarks and installed
Codex Keep/blocker/reconnect checks pass. At 10,000 completed jobs, idle activity
reads decreased from 377 ms to 0.069 ms; this is registry timing, not edit latency.
Milestone 5’s actual card checks subsequently passed with manual observations;
Computer Use still cannot access Codex.

[Beta 8 milestone 3 — incremental native cleanup](beta8-milestone3/README.md)
keeps operation ownership until Undo groups and precision settings finish
cleanup. Its 2,320 regressions, native harness checks and 100 benchmark runs pass;
the report records shorter cleanup pauses and increased typed elapsed time.
Installed/editor qualification now passes in both formats; the follow-up records
an editor-specific inventory correction, 2,322 passing tests and separate Codex/local timings.

[Beta 8 milestone 2 — scope-proportional typed preparation](beta8-milestone2/README.md)
implements exact named-width lookups, metadata-only color preparation and exact
nullable-node-name recovery. Source/native parity checks and 140 benchmark runs pass, with the small-case
polling regression disclosed. The rebuilt candidate is installed and qualified
in the joint milestone 2/3 editor report.

[Beta 8 milestone 1 — native-script capacity](beta8-milestone1/README.md)
removes the script target-count ceiling while retaining the 4 MiB request budget.
Tests-first regressions, native capacity/recovery checks and installed Codex
workflows pass; the rebuilt MCP candidate is installed. All 150 benchmark runs
(five per case) pass. This record preserves the timing trade-offs and editor
limitations and does not supersede earlier unperformed release/card gates.

[Unified results and faster typed edits — September 26, 2026](unified-results-20260926/README.md)
adds typed Keep, shares successful-result countdowns, and prepares selected simple
typed edits natively without source copies or workers. Source checks, native
route-parity tests and all 320 paired benchmark runs pass. Installation and
editor/client qualification remain pending the unsaved-document decision.

[Automatic Keep countdown — September 26, 2026](auto-keep-countdown-20260926/README.md)
adds the requested 30-second default Keep, progress bar and **Wait for my answer**
opt-out. It is built and regression-tested; installation waits for the user's
decision about the currently unsaved Dactylotype document.

[Finish and qualify native scripting — September 26, 2026](native-scripting-qualification-20260926/README.md)
implements the six focused fixes and installs the corrected candidate. It records
2,231 passing Python tests, 67 isolated native scripting checks, retained typed
recovery checks, 60 fresh-process benchmarks, actual editor Save/Restore and
installed Codex text/reconnect workflows. Live fault/overwrite probes and an
unattributed interaction observation remain explicit limits; see that report
before treating the milestone as unconditionally signed off.

[Simple native scripting — September 26, 2026](simple-native-scripting-20260926/README.md)
removes the unpublished scoped and snapshot script branches, keeps one native
execution route, and uses saved-version reload for script recovery. The candidate
passes 2,208 regressions plus two separate socket tests, 60 built native fixture
checks, and 50 fresh-process benchmark runs. Installation, actual editor saving
and restoration, and the installed chat-client gate await authorization; this
record does not claim the milestone complete.

[Conversation workflow — September 22, 2026](edit-workflow-20260922/report.md)
implements the shared MCP App, text contract and save/resume coordinator. Python,
installer, packaging and transport gates pass. The authorized Beta 6/build 48
installation and normal-editor Save and continue, Undo/Redo, discard, preview,
and separate final Save As now pass. The subsequent
[save UI retest](edit-workflow-20260922/retest/report.md) verifies real card saves
in Claude and Cursor, but holds Beta 6 for a failing Claude text save fallback,
Cursor stale-state/permission-timeout UX, and the still-blocked Codex inline
check. Exact tested client versions and native evidence are recorded there.

Latest full native-coding qualification: **RV02, September 14, 2026**, committed in
`5666e289`. This is the private `2.0.0-beta.1` candidate, installer build 43,
tested in Glyphs 4.1 (4107). These records are evidence from specific runs;
they do not establish public-release readiness or the identity of a later process.

The subsequent [v1 → v2 feature and intent audit](v1-v2-feature-audit-20260914/report.md)
maps all 87 active v1 tools, distinguishes deliberate reductions from unresolved
workflow gaps, and identifies incompatible installed skills plus separate,
unintegrated master-compatibility work. It is a review, not a new native benchmark.

[The gap-fix implementation plan](beta1-gap-fixes-plan-20260914/plan.md) starts
with six high-priority steps. Each has a test gate and a short explanation of
the next fix; the plan itself does not claim implementation or qualification.

[H1 skill cleanup](beta1-h1-skills-20260914/report.md) is implemented and installed:
seven obsolete private instruction folders archived with exact backups, eleven
current managed skills verified, 130 installer and 46 Python tests passed. The
unchanged Starter wording assertion remains logged; the full desktop suite is
not claimed clean at the H1 gate; H2 resolves that assertion below. Runtime
identities were unchanged during H1.

[H2 setup/identity correction](beta1-h2-setup-20260914/report.md) aligns current
migration, release and skill guidance, installs the updated release skill, and
resolves the Starter assertion noted in H1. All **179 macOS** and **70 focused
Python** tests passed (one optional Python skip); the documentation build passed.
Desktop labels were corrected in source but the app was not reinstalled during
H2; runtime identities were unchanged at that gate.

[H3 compact context](beta1-h3-context-20260914/report.md) is implemented, installed
and qualified in Glyphs 4.1 (4107): native current-font evidence, toolbar master
and bounded selected glyph names through the seven-tool interface. All 649 lean
regressions, 133 isolated native selection checks and 102 distinct installed
native checks passed after two documented harness corrections. Median context
HTTP reads were 23/26 ms for small/bounded selections; queue tails remain separate.

[H4 bounded glyph discovery](beta1-h4-glyph-discovery-20260914/report.md) is installed
and qualified: native names in pages of up to 100, explicit coverage and stale-cursor
handling through `read_entities`. All **713 lean**, **38 isolated native** and
**616 installed native** checks passed, including a 1,272-glyph Roboto Slab inventory.
Native callback p95/max were 21.35/40.39 ms; document-discovery and queue tails remain
separate.

[H5 layer discovery](beta1-h5-layer-discovery-20260914/report.md) is implemented,
installed and functionally qualified: exact native layer IDs, associations and
requested classification flags in bounded pages. **796 lean**, **164 isolated native**
and **302 installed native** checks passed; 54 follow-up checks also passed.
One original callback exceeded the 200 ms maximum (339 ms); it did not recur in
21 focused reads. The original timing exception remains recorded.

[H6 kerning discovery](beta1-h6-kerning-discovery-20260914/report.md) is implemented,
installed and qualified: native group/key fields and bounded stored-pair pages in
LTR/RTL/vertical through the same seven tools. **875 unique lean cases**,
**155 isolated native checks** and **1,087 installed assertions** passed across
the recorded gates. One live harness-attribution failure was corrected and
preserved. Native callback p95/max were **24.78/64.35 ms**; HTTP/queue tails
remain separate. All eleven skills and both running component hashes match the
candidate. Its next step is covered by M7 below.

[M7 master properties](beta1-m7-master-properties-20260914/report.md) is implemented,
installed and qualified: requested fractional native defaults, italic angle and
bounded internal/external axis positions. **942 lean regressions, 74 isolated
native checks, 431 installed assertions and 50 delivery checks passed.** Native
read callback p95/max were **26.86/31.69 ms**. Initial harness failures, the native
opening dirty-state control and HTTP/queue tails remain recorded separately.
Both running hashes and all eleven installed skill payloads match the candidate.
Step 8 (production name, script and layer count) is paused for feedback.

[The follow-on plan for gaps 7–14](beta1-medium-gap-fixes-plan-20260914/plan.md)
covers requested native read fields and bounded diagnostics, followed by precise
native editing and OpenType convenience recipes. Step 7 is delivered above;
the remaining steps require their own tests, reports and user feedback. These
gap numbers are separate from the earlier P-series benchmark sequence.

## Current result

[RV02 native-coding follow-up](rv02-native-coding-20260914/report.md) implemented,
installed and verified eleven managed skills, including current OpenType routing,
native precision guidance and qualified Glyphs 4 API notes. It records 150 passed
checks, zero failed and one unverified populated-hint case. The official offline
documentation corpus is unchanged. [Agent assessment](rv02-native-coding-20260914/judgment.md)
and [execution log](rv02-native-coding-20260914/action-log.md) distinguish measured
results from judgment and first-attempt friction.

Scripts are written with file tools and run through native Glyphs routes. The
MCP interface remains seven tools and five jobs; RV02 adds no script-execution
or feature-editing MCP tool and makes no latency improvement claim.

RV02 recorded runtime identities were sidecar `2.0.0-beta.1+82daa62ac227` and
bridge `2.0.0-beta.1+8b74a8d27ae4`. Full fingerprints, release metadata and host
identity are in [RV02 status evidence](rv02-native-coding-20260914/runtime-final.json).
The [installation receipt](rv02-native-coding-20260914/installation.json) and
[backup proof](rv02-native-coding-20260914/backup-evidence.json) document the skill
update; the runtime was unchanged during that update.

## Report index

| Record | Scope and later status |
|---|---|
| [Beta 8 milestone 6](beta8-milestone6/README.md) | Opt-in font checkpoints, action evidence, history/restoration and project template. Installed editor, Codex and desktop qualification; costs and remaining limits disclosed. |
| [Repository consolidation](repository-cleanup-20260914/report.md) | Remaining Beta 1 desktop/docs/release work validated for commit: 1,914 Python and 179 macOS tests passed, two optional skips. Test isolation corrected; installed runtimes unchanged. |
| [M7](beta1-m7-master-properties-20260914/report.md) | Native master metrics, angle and axes; installed and qualified, step 8 paused. |
| [Gaps 7–14 plan](beta1-medium-gap-fixes-plan-20260914/plan.md) | Accepted read extensions and native recipes; step 7 is delivered in M7. |
| [H6](beta1-h6-kerning-discovery-20260914/report.md) | Stored kerning discovery; installed and qualified, next step paused. |
| [RV02](rv02-native-coding-20260914/report.md) | Latest focused native-coding implementation and installed qualification. |
| [RV02 plan](rv02-native-coding-plan-20260914/plan.md) | Accepted scope and acceptance criteria. |
| [RV01](rv01-realistic-20260914/report.md) | Twelve realistic Roboto Slab tasks. RV02 addresses its skill/API findings and completes its pending UI cleanup. |
| [Native grouping correction](dirty-grouping-20260914/report.md) | Minimal existing-hook change. Its pending installation/UI checks were subsequently completed in RV01 and confirmed in RV02. |
| [Dirty-indicator investigation](dirty-indicator-20260914/report.md) | Native data restoration versus document dirty-state behavior; historical observations retained. |
| [HTTP route correction](http-route-fix-20260914/report.md) | Serve the configured endpoint directly. This does not resolve all HTTP/queue tails. |
| [P13 improvement](p13-curvature-improvements-20260913/report.md) | Curvature display and realistic-font qualification. |
| [P13 paired baseline](p13-curvature-display-20260913/report.md) | MCP versus native companion/UI access, including historical v1 results. |
| [P12 final checks](p12-final-checks-20260913/report.md) | Completes the outstanding slant controls; retains derived-bounds and crash limitations. |
| [Crash guidance](crash-guidance-20260913/report.md) | Bounded recovery instructions, with permission required before temporarily pausing autosaving. |

## Remaining limits

- Populated-hint preservation is unverified in RV02; its edited layers had no hints.
- HTTP/queue latency tails and the earlier autosave crashes remain separate
  investigations. Successful bounded runs do not establish a crash root cause.
- Native Redo→Undo dirty-state behavior is accepted as Glyphs parity. Exact
  restoration does not imply every history path clears the document indicator.
- Selection Lens label/position polish and clearer malformed-selector wording
  remain deferred. Neither requires a new MCP tool.
- RV02 does not remeasure v1 or replace the earlier paired benchmark results.

## Evidence and maintenance

Preserve earlier reports and their measurements. Each `coverage-index.md` is a
historical snapshot from the original benchmark workspace; its relative links
may refer to that workspace. Use the direct links above for the committed records
in this checkout. Do not mistake a historical pending status for the latest result.

RV02's [evidence manifest](rv02-native-coding-20260914/evidence-manifest.json)
records the archive checksum and each member's checksum. Keep the archive,
manifests, native proofs and preserved user-font copies. The build directory also
contains evidence and source worktrees; cleanup must use inspected generated
outputs, never a blanket removal of `build/`.
