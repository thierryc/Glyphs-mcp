# Beta 8 development validation

Source target: `2.0.0-beta.8`, desktop build **50**, branch `lit/v2-beta`.
Status: **all accumulated source is consolidated in `3cf956ab`; the combined release gate passes, and the matching desktop/MCP components are installed locally. A universal Developer ID signed candidate is built. Apple notarization awaits explicit upload authorization. Milestone 8 group-pair native UI Undo, new pair-card visual acceptance, and signed-update/migration gates remain open. No Beta 8 publication.**

The [Beta 8 milestone plan](BETA8-MILESTONES.md) starts with removing the native
script target-count ceiling. Every milestone begins with regression tests and
ends with a separate verification report. The user now authorizes continued
milestones and necessary saving unless an unresolved issue prevents continuation.
Milestone 5 has installed path, spacing and kerning qualification. Milestone 6 adds qualified opt-in Git checkpoints
and a Git-enabled font project template; consolidation moves to milestone 7 and
exact typed kerning edits/language-aware discovery move to milestone 8.
The [checkpoint contract](BETA8-GIT-CHECKPOINTS.md) is implemented; checkpointing
remains disabled unless explicitly enabled for a project. Consolidation (milestone 7) is complete. Milestone 8 implementation and standalone native qualification are recorded in [its report](reports/beta8-milestone8/README.md); installed follow-up is recorded below.

- Advanced `release.json`, app beta identity and both Xcode build configurations
  with the existing version helper, after a dry run.
- Updated current v2 guidance, release reference, metadata assertions and the
  synchronized eleven-skill package. Twelve tools and protocol 1 are unchanged.
- Preserved the signed Beta 7 tag `190d25c5`, its verified published assets
  and evidence in [BETA7-VALIDATION.md](BETA7-VALIDATION.md).
- Beta 7 is published with verified public downloads and its exact signed beta
  feed. Its signed-update/component-migration test remains unperformed and is
  disclosed in the release notes. Stable Latest and pinned Glyphs 3/v1
  documentation are untouched.
- Removed all generated repository builds after Beta 7 public verification,
  including release/test artifacts and signature utilities. Three cleanup
  passes removed 5,725,506,914 bytes by logical file size; this is not a
  physical-space measurement. Source worktrees and installed runtimes remain.
- Publication follow-up: 30 focused tests, eleven-skill synchronization and the
  documentation production build passed before generated output was removed.

Metadata, documentation, synchronization and package checks are recorded below.
The initial metadata checks below are not signed-release qualification. Native
milestone evidence is recorded separately at the end of this document.

## Initial metadata checks — September 27, 2026

- 30 focused metadata, version-bump, documentation and release-skill tests passed.
- Eleven canonical/packaged skills match; lean package checks pass with twelve
  tools and both runtime architectures.
- Documentation production build and patch-whitespace checks passed.
- Before publication, the signed appcast was unchanged from the Beta 7 tag.
  After public download verification, it was replaced by the exact signed
  Beta 7 release appcast; no Beta 8 feed item was generated.
- At this initial metadata-preparation stage, no Beta 8 tag, application build,
  installation or publication was performed.

## Milestone 1 — native-script capacity

The [milestone report](reports/beta8-milestone1/README.md) records tests-first
development, 2,291 passing regressions (two skips), real native qualification in
both font formats, and installed Codex execution/saving/cancellation/restoration.
The MCP-only candidate was rebuilt into the established target, installed and
loaded with matching source/build/install identities. Existing inspectors and
settings were preserved. All 150 fresh-process runs (five per case) passed after correcting
a documented temporary-path setup error in the save benchmark. The report
separates local native timings from installed-client latency and records the
remaining editor and responsiveness limits. Later milestones had not started
at the milestone 1 handoff.
No Beta 8 release tag or publication exists.

## Milestone 2 — scope-proportional typed preparation

The [milestone 2 report](reports/beta8-milestone2/README.md) records tests-first
implementation, 2,307 passing regressions (two skips), native route parity and
exact node-name recovery in both formats, and 140 passing fresh-process
benchmark runs. Named widths use exact lookups; colors prepare detached metadata.
The report discloses the one-color polling regression, near-full-font limits
and unchanged peak memory. Canonical guidance and packaged mirrors match.

The candidate is rebuilt into the established target with verified source/build
identity. It is **not installed or editor-qualified yet**: Dactylotype remains
open and dirty, and the save/close decision is pending. No unrelated font was
saved or closed. Milestone 2 remains incomplete; milestone 3 had not started at
that handoff.

## Milestone 3 — incremental native cleanup

The user subsequently requested the next milestone. Its [delivery report](reports/beta8-milestone3/README.md)
records tests-first cleanup work and native comparisons separately. This source
continuation does not complete milestone 2's installed gate. Dactylotype remains
untouched, and milestone 4 has not started.

Milestone 3 passes 2,320 regressions (two existing skips), focused native cleanup
and retained typed/script recovery checks in both formats, and all 100 benchmark
runs. Cleanup pauses decrease substantially; typed elapsed time increases and
the report records that trade-off. The candidate is rebuilt with matching source
and built files, synchronized skills and passing package checks. The final live
read still finds Dactylotype dirty and milestone 1 loaded. Installation and actual
editor/client qualification remained incomplete at that source handoff.

## Installed qualification follow-up — September 27

The [actual editor report](reports/beta8-milestone3/editor-qualification.md)
closes the milestone 2/3 installation gates in both font formats. Actual Save,
selective Undo, native Undo/Redo, saved-version reload/fresh bindings and partial
script failure recovery pass. Large 4,096-width jobs preserve all 904 controls
and restore rounding/Undo settings across 5,000 glyphs. The installed card Keep
timeout and text opt-out were observed; full visual card testing stays in M5.

Editor sampling exposed repeated window-order queries omitted by the standalone
harness. A failing regression test preceded the focused native inventory fix.
The corrected rebuild is installed and loaded with matching identities; 2,322
tests pass, two skip. Existing companions/settings and Dactylotype were preserved.
The new report separates Codex verification latency, local MCP editor timing
and the unchanged five-run benchmark matrices. No commit/publication occurred.

## Milestone 4 — active-work polling

The [history-scaling report](reports/beta8-milestone4/README.md) records tests-first
changes, **2,338 passing regressions and two skips**, 80 final paired benchmarks,
source/build/install identity verification and actual installed Codex lifecycle
checks. Unchanged native-result reads preserved job bytes, modification time and
workflow revision. Sidecar restart retained the result and blocker; stale actions
were rejected, Keep released the next task, and fresh reads verified exactly-once
edits and an untouched control. The disposable font was saved under the user's
continuation authorization. Dactylotype was reopened clean and unchanged.

At 10,000 completed jobs, median idle activity polling decreased from 377.381 ms
to 0.069 ms, and active polling from 368.171 ms to 0.131 ms. The empty-history idle
case increased by about 2.6 microseconds. These are synthetic registry timings;
startup and memory still grow with retained history. Raw ranges, CPU, memory,
record-copy/read/write counts and separate installed-client evidence are retained.

Milestone 5 is not started. Computer use explicitly refuses access to the Codex
app, so its required visual card checks need manual help. This is not an MCP
connection failure and does not justify substituting mock-host tests for the
installed card gate. No commits, publication or plugin-cache edits were made.

## Milestone 5 — conversation overhead

The [delivery report](reports/beta8-milestone5/README.md) records tests-first cache,
identity and late-response fixes, intended-effect summaries and leaner routing.
The full suite passes 2,348 tests (two skips); 12 final focused checks also cover
the subsequent blocking-summary guard. The rebuilt MCP-only candidate is installed
and its path, spacing and kerning tasks passed through Codex on a disposable real
font. The final card gate passed September 28 with user-observed Details, literal
output, hidden countdown and Wait behavior, corroborated by action records. A real
42-second sidecar disconnect/reconnect preserved the same result and opt-out without
replay. The final nine-layer fractional-width test was selectively undone; its saved
fixture hash returned to the original. All five open fonts are clean, with no active
operations. Computer Use remains blocked; the report distinguishes user visual
observations from transport/server evidence. Current focused regressions pass 47
tests. No production changes, additional rebuild, commit or publication were needed
for this qualification. Milestone 6 is recorded below.

## Milestone 6 — Git checkpoints and project template

The [delivery report](reports/beta8-milestone6/README.md) records the opt-in project
policy, exact saved baselines, font-only Git transactions, action records,
bounded history/comparison and editor-coordinated historical restoration. The
desktop app includes project settings and the explicitly Git-enabled template.

Tests began with failures. Final qualification passes 2,404 Python tests (three
skips), 214 desktop tests, twelve-tool/package checks and eleven-skill sync.
Both real-font formats passed actual editor saving, partial-failure restoration,
fresh bindings, native content/Undo verification and Git-only retry. Installed
Codex workflows exercised Keep, Save As, manual-save continuation, duplicate
Save and restart reconciliation. Desktop template/settings/history/visual
comparison/restoration passed through the installed app.

Twenty fresh native-process controls report the additional cost of checkpointing
using the standalone GSFont writer; they are separate from actual editor Save
tests. Actual editor Save/checkpoint medians were 1.985 seconds for `.glyphs` and
2.560 seconds for `.glyphspackage`. Batched Git materialization reduced measured
package restoration to a 2.879-second median. All ten final editor restore/save
repetitions passed. Ranges, stage boundaries, memory and measured main-thread
durations are retained; no new responsiveness guarantee is made.

The final installed/loaded sidecar hash starts `56caaeb5922e`; the bridge starts
`c35ab0983487`. Source, build receipt, installed app and loaded identities match.
Only the MCP runtime component and matching desktop app were updated; companions,
settings and plugin caches were preserved. Existing font projects were not opted
in. Dactylotype was not edited or saved. The milestone-5 visual Codex-card gate
remains open. Stop before milestone 7; no implementation commit or publication.


## Milestone 7 — Consolidation qualified locally (September 28)

[Report and evidence](reports/beta8-milestone7/README.md). Tests preceded changes.
Tool descriptions decreased from 17,401 to 12,962 UTF-8 bytes (25.51%) while
preserving all twelve schemas and metadata. Corrected stale current instructions,
labeled historical plans, consolidated duplicate export hashing and replaced
source-line budgets with architecture/package contracts. Eleven skills remain
synchronized and the existing v1 snapshot is unchanged.

The final Python suite passes 2,414 tests (three skips, five warnings). Rebuilt and
installed the MCP component and matching desktop app under existing authorization.
Fresh catalog, source/build/install/loaded identity checks and an actual Codex OTF
export/publication into an ignored local test folder pass. The sidecar identity
starts `bb5297f858c9`; unchanged bridge `c35ab0983487`. All five documents were
reopened clean without saving; no active operations remain. No Swift source or
editing algorithm changed, so prior desktop/native-edit measurements remain prior
evidence. The visual Codex-card and signed-update/migration gaps remain open.
Stopped before milestone 8. No commit, staging or publication.


## Milestone 5 final card qualification — September 28 follow-up

The earlier open-card notes in milestones 4, 6 and 7 record their completion-time
state. That gap is now closed by the [final milestone-5 report](reports/beta8-milestone5/README.md#final-qualification--september-28).
Loaded identities still match milestone 7. The separate signed Beta 7 updater and
component-migration qualification remains open. No milestone 8 work was started.

## Combined candidate preparation — September 28

The user authorized consolidating all accumulated Beta 8 work, local installation,
and signing the release candidate. Work is consolidated on `lit/v2-beta`; the
stable branch and published Beta 7 appcast remain separate.

The desktop checkpoint browser now uses the existing comparison workspace.
Nine focused Swift tests passed. Additional native model checks covered rapid
selection, late responses, pagination counts, fixed endpoints and restoration
of the working-file selection/filter. Native SwiftUI views were rendered at
wide and narrow sizes with sample data. Live font restoration was not exercised
by this UI-only qualification.

The earlier blocked installer processes have exited. The existing transactional
MCP-only installation completed successfully from `build/simple-native-scripting`,
retaining port 9680, auto-start and both installed companion identities. This
updates installed files; loaded bridge and editor qualification are recorded
in the [combined candidate report](reports/beta8-release-candidate/README.md).

The complete local release gate passes 2,464 Python tests (two skips) and 219
desktop tests. Both installed kerning formats pass all 36 lifecycle cases each.
The actual Codex connector completed proof pagination and exact-edit
preview/apply/Keep/Save checks. Glyph-pair native Undo/Redo passed; group-pair
Undo through the ordinary Glyphs menu did not change the value, so that gate
remains unresolved. The disposable values were restored and saved; all seven
open documents are clean, including the five reopened documents from the prior
session. Dactylotype was neither edited nor saved.

The fresh verified desktop app is installed at `/Applications/Glyphs MCP.app`;
the previous app is retained under `build/local-install-backups/beta8-20260928/`.
The installed picker, empty comparison, glyph comparison, details sheet, restore
confirmation/cancel and return to working selection passed a native UI smoke
check. The universal release app at `dist/installer-app/Glyphs MCP.app` is
Developer ID signed with a secure timestamp; 94 Mach-O binaries and 47 bundles
verify. It is not notarized. Automatic approval review rejected Apple submission
until the user explicitly authorizes uploading those artifacts to Apple.
No Beta 8 release tag, public release or feed update was created.
