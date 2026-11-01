# Path Doctor cleanup qualification — 2026-11-01

Initial qualification used isolated candidate modules through the existing
recoverable script workflow. A subsequent explicitly authorized local install
and restart loaded bridge/sidecar 2.5.0 (build 73); installed acceptance is below.
No desktop release was published. The separate online skill/catalog was updated.

## Implemented

`path_cleanup` uses the existing job/preparation/patch workflow. There are no new
top-level tools. Settings select exact duplicate LINE removal, separately selected
closing-seam normalization, collinear line removal, or explicitly selected bounded
near-node removal, handle alignment and native curve simplification. Defaults are
exact duplicates, 0.5 font units and 2 degrees maximum handle rotation.

Candidates are prepared on detached layers, in deterministic order, with fixed
address matching across ordinary masters, brace layers and complete explicit
bracket branches. Unknown specials, sparse bracket branches and incompatible
source topology are held. Every affected layer must qualify. Native fitting may
move geometry but must preserve surviving authored flags, metadata, contour
starts, other contours and unrelated layer data. Exact duplicate runs retain the
earlier node; closing boundaries retain the separately selected seam rules.

Bounded edits compare cumulatively against the original outlines, use symmetric
boundary upper bounds, and certify contour separation using monotone Bézier
pieces and enclosing control hulls. Unresolved intersections/tangencies are held.
Native samples include authored locations, active export-instance locations,
pairwise authored midpoints and both sides of bracket boundaries. Exact sampled
comparisons retain real segments and endpoint profile semantics. Sampling is not
a continuous designspace guarantee. Bounded editing is limited to closed filled
line/cubic paths. Stroke/Pen-profile optimization remains a separate workflow;
component-dependent interpolation is currently held.

The existing card contains the settings, numeric fields/sliders, Analyze and
Apply cleanup. Updates are revision-bound, keep the glyph scope fixed and
invalidate stale proposals. Analysis works without saving. Application retains
existing save prerequisites, warning review, stale-state and recovery behavior.
Applied results retain Keep, Undo and Save, with native Last Saved comparison.

## Verification

234 relevant Python/bridge/workflow/card/skill/recovery tests passed. Coverage includes duplicate
runs and exclusions, metadata/profile conflicts, special-layer correspondence,
intermediate failures, cumulative budgets, unexpected native side effects,
settings replay/staleness, analysis lifecycle and card interactions. The shared
skill copies synchronize and the lean candidate package builds successfully.

Glyphs 4.2 (4202), `com.GeorgSeifert.Glyphs4`, passed eight detached native cases:
ordinary-master, brace and bracket exact cleanup with repeat-pass idempotence;
bounded near-node removal; handle alignment; curve simplification; and bounded
brace/bracket cleanup. Native trial application and exact snapshot restoration
were checked. Consecutive-duplicate identity retention and native NSUndoManager
Undo/Redo passed independently. Capabilities are gated to this qualified host
and the existing native-removal/attribute selector checks.

A separately authorized three-master disposable was scanned across 1,844 glyphs,
5,532 ordinary master layers and 2,880 paths. Its full exact pass removed 270
redundant seam nodes in 228 layers; three seam findings remained because of one
coordinated profile conflict. Unmodified stored outline hashes were retained and
a repeat pass proposed no further changes. This full pass preceded the final
sample-validation additions; the final native fixture suite exercises those
additional checks. These counts do not mean every diagnostic is an error or that
all paths were repaired. The disposable's pre-pass baseline alone was saved with
explicit permission; applied edits remain unsaved for reference review.
An independent fresh live-original versus disposable comparison then found zero
real-geometry or endpoint-profile differences across all 2,880 paths. Fifteen
detached native stroke-expansion samples across the three masters matched
exactly. The Changes Against Reference view was activated with Last Saved on
the disposable; colored native editing contours alone are not difference proof.

## Privacy and limits

Private font files, live reports, geometry and UI evidence stay under the ignored
`.codex-local/` tree. Public fixtures contain original generic geometry only.
The Last Saved overlay is visual review, not a geometry certificate. Saving can
serialize native values at reduced precision and advances that reference. Native
script whole-font recovery is distinct from typed selective Undo. No release or
installed-card acceptance was claimed by the initial source-only handoff.

## Installed acceptance and online skill

The final loaded bridge fingerprint is
`sha256:3645c23bf2c9f081193e71df08b47fe25b41aa8a73415066abddb12123d5fd3d`;
the installed sidecar fingerprint is
`sha256:358a21ced002453ea6b6b84258482c25ed5b695a984a4f8c8071a52856d7a6d1`.
Fresh native status confirmed bridge 2.5.0, `path.cleanup.v1`, the duplicate
write capability and the `path_cleanup` job kind. Live discovery caught a missing
recognized-capability entry; it was corrected and covered by a regression test.
The affected protocol/sidecar/cleanup suite passed 40 tests after that fix.

The installed workflow removed one redundant node on an original generic
five-node square. A fresh read showed four surviving nodes with expected
coordinates. Its offered typed Undo restored the complete five-node path,
including the duplicate's original position and flags. No result Save occurred.
The optional card was requested for the three-master disposable with fixed
all-glyph scope, default duplicate-only settings and Automatic Keep disabled.
Its read-only preparation found no remaining eligible duplicates across 5,532
master layers. Expanded side-panel rendering was not available to UI automation;
card interaction coverage remains the automated host tests plus live workflow
responses, rather than a claimed manual click-through.

Eight open fonts were preserved as separate native recovery files before
restart, and their glyph/master inventories were checked on reopen. The user
also quit/restarted Glyphs during installation. All eight fonts were reopened
after the final install, using their existing sources where available and the
recovery files for previously untitled fonts. Recovery files remain local;
session-local Undo/history does not survive a Glyphs restart.

The online skill content and immutable catalog pin were published through
`thierryc/glyphs-mcp-skills` PRs #7 and #8 after passing catalog validation.
The catalog pins source commit `ed845b1819c044e51b69bb37c724e030a96a9785`
and codeload SHA-256
`e87e75f9a82dc535ab436f7c4a98ef45ed4eaaee41bea234678af1f5c85af52d`.
