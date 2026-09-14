# Lean v2 benefit queue

Implement one item at a time. Native Glyphs operations remain the write
mechanism wherever they satisfy the requirement; additional workflow code must
have a demonstrated benefit. Preserve external computation, compact patches,
fractional coordinates, and the existing seven MCP tools.

## 1. Spacing — passed

Implemented `start_job(kind="spacing")` using native intersections outside the
editor and the existing width/translation patches. Automatic reference policy
uses H for uppercase, x/n/o for lowercase, and one/zero for figures. Explicit
references have no silent fallback. Per-layer reports include the selected
reference, fallback, preservation reason, and unavailable targets.

Preserve individual fractional tabular widths instead of importing v1's median
integer width. Keep zero-width marks, metric keys and native alignment. This
initial workflow selects master layers; special layers and a general optical
spacing guarantee are outside its claim.

The real native V/W/Y fixture measures approximately −114.818-unit bearings with
x and +8.556-unit bearings with H. Native apply/discard checks cover fractional
input coordinates, anchors, exact width restoration and geometry fingerprints.
Native translation is retained; its shape-cache invalidation and operation-scoped
rounding guard are necessary additions demonstrated by the integration gate.
Physical bearing verification uses output coordinates: native displayed metrics
and cached display paths can be rounded while node coordinates remain fractional.

The isolated gate is `scripts/qualify_simple_v2_spacing_native.py`, executed by
`glyphs run --quiet --app '/Applications/Glyphs 4.app' --plugins ''`.
Evidence is in `build/spacing-native-benefit.json`. The source/backup record for
the editor gate is `build/lean-benefits-current.json`; the source font is never
edited. Editor acceptance passed again on 189 Dactylotype master layers after
adding component context: 333 changes, 36 preserved-width or mark layers, exact
apply and discard restoration. Preparation, apply and discard p95 bridge response
times were 13.153, 17.044 and 15.595 ms; the maximum was 86.200 ms, including two
seconds of post-operation sampling.
Both saved source hashes remained unchanged. See `build/spacing-live-acceptance.json`.
The HTTP gate also exposed per-request worker cancellation; cleanup now occurs
only when the server transport exits, covered by HTTP and shutdown regressions.
Detached copies retain glyph context to resolve components. Only the external
worker's private, never-saved font disables the native display grid, which otherwise
rounds parented bounds despite exact node coordinates. The editor's grid stays
unchanged. Native curve-extrema approximations are excluded from translation
verification: hashes compare output coordinates to the intended fractional shift.
The full suite and deterministic build results are recorded with item 2 below.

## 2. Kerning collisions — passed

Native `GSLayer.nextKerningForLayer:direction:` supplies effective values, including
groups and exceptions (installed Glyphs 4.0.1 SDK `GSLayer.h`, kerning section).
The custom policy retains the tested two-pass refinement and computes only the
fractional loosening needed for the specified sampled clearance. Exact pair
exceptions avoid changing unmeasured peers. An explicit patch/read carries master,
direction, pair keys and nullable values. The bridge uses native set/remove calls.

The real native fixture reproduces +12 coarse / −8 refined clearance. Independent
polygon-coordinate measurement verifies corrected clearance, including existing
zero and fractional exceptions; discard restores exact presence and value.
The group peer remains unchanged. See `build/kerning-native-benefit.json` and
`scripts/qualify_simple_v2_kerning_native.py`. The workflow supports LTR geometry;
RTL and vertical remain distinct explicit storage domains, with no collision claim.
The bridge budget rises from 1,500 to 1,600 lines for these tested native mechanics.

Installed editor acceptance examined 126 Dactylotype master pairs, corrected nine
controlled collisions and left 117 clear pairs unchanged. Exact application and
discard passed, followed by removal of all fixture collisions. Preparation/apply/
discard p95 response times were 4.795/4.889/7.261 ms; the maximum was 21.861 ms,
with two seconds of post-operation sampling. Evidence:
`build/kerning-live-acceptance.json` and `build/kerning-live-fixture.json`.
The full suite passed: 2,036 tests, 5 skips. Deterministic builds matched and
`git diff --check` passed. The original font remained byte-identical.

## 3. Start-node correspondence — passed

Retained the tested landmark descriptor and matching policy externally, with a
compact native cyclic-reorder patch. The selected reference phase stays unchanged,
which makes a repeat a no-op. Native `GSPath.makeNodeFirst:` places its chosen
start at the end of the array; the bridge accounts for that indexing directly.
The native three-master fixture reports corresponding landmark indices 0/2/3.
Square and cubic contours keep identical geometry, original node objects and
user data, and hint-node references. Exact discard and idempotence pass.
See `build/start-node-native-benefit.json`.

The protocol budget increases to 350 lines for the explicit contour index,
node count, shift and hash contract; the bridge remains below 1,600 lines.
The workflow selects one explicit contour per glyph. It rejects ambiguity and
incompatible/open contours, and makes no arbitrary master-repair claim.

The installed editor gate aligned eight controlled `o` contour offsets across
nine masters. Native Undo and Redo, a zero-change repeat after Save, exact discard
and fixture cleanup all passed. Preparation/apply/discard p95 responses were
8.061/15.838/10.534 ms; apply's maximum was 18.298 ms. Every saved font-data file
was restored byte-for-byte. Only `UIState.plist` changed from opening the proof tab;
the original font stayed byte-identical. See `build/start-node-live-acceptance.json`.
The full suite passed: 2,049 tests, 5 skips. Repeated builds and diff checks passed.

## 4. Optional straight-stem preservation — passed

Implemented `start_job(kind="slant")` with native slant on external detached
layers and optional `preserveStraightStems`. The real rectangular fixture sets
native horizontal/vertical stems, then compares raw slant, Cursivy and the native
thickness-only option at 12°. Each retains 97.814760 units perpendicular to the
slant from a 100-unit source. The narrow custom pass measures 100.00000000000001
from output coordinates. This comparison establishes this fixture's objective,
not a general judgment of native Cursivy or a balanced-italic claim.

The retained custom subset only detects and corrects accepted straight stems.
Curve-adjacent sides, conflicting candidates and unsafe deltas are excluded.
The existing 350-line protocol and 1,600-line bridge budgets still hold, including
bounded coordinate vectors, topology guards and native node/anchor/component setters.
Node objects, metadata, hints, advances and fractions survive application and
exact discard. Native matrix copies prove both application and restoration
before any live setter runs. Native matrices that cannot round-trip exactly
reject preparation, including the demonstrated unequal-scale/skew case.

Anchors follow native slant. Manual component composition avoids double shear
when a base master is selected. Automatic component layers retain their local
data and are reported as skipped; their displayed outlines can inherit edited
bases. Special layers and arbitrary smart-component correction are outside scope.
Native evidence: `build/slant-native-benefit.json`.

The installed disposable Dactylotype gate applies 729 outline layers across nine
masters, including 66 accepted straight-stem pairs. Exact coordinate read-back,
unchanged advances, exact discard and saved font-data restoration passed.
The source original stayed byte-identical; only disposable `UIState.plist`
may differ following proof navigation. The gate samples responsiveness through
two seconds after each operation. Final measurements are in
`build/slant-live-acceptance.json`; the earlier successful run is retained in
`build/slant-live-before-final-guard.json`.

Reproduction: run `scripts/prepare_simple_v2_slant_live.py` in an isolated native
Glyphs process, then `scripts/qualify_simple_v2_slant_live.py apply`, inspect the
proof in Glyphs, run `discard`, save the restored disposable copy, and run `finish`.
The acceptance record resolves the sole disposable document and checks the
original source hash before every phase.

Final preparation/apply/discard p95 bridge responses were 10.126/20.003/19.023 ms;
the maximum was 30.623 ms. All 729 target hashes and advances restored exactly,
and saved font-data comparison passed. The complete suite passed: 2,076 tests,
5 skips. Repeated builds matched and `git diff --check` passed. The final core
sizes are protocol 340, bridge 1,592 and sidecar 2,218 lines.

The redesigned server window and compact bridge palette remain installed. After
restart, Edit → Glyphs MCP Server displays Start/Stop, editable MCP port, version
2.0.0 (Bridge 0.1.0), author, GitHub and support links. Comparison Reference shows
the active saved filename. Native checkmark/tooltip contracts were previously
verified; menu screenshots remain unavailable through this UI capture provider.
Applied/restored proof and server-window captures are in `build/`.

Custom Tunni, general compensated scaling, custom smoothness repair and a full
balanced-italic engine remain outside the queue. Each item's claim is limited
to the supplied benefit evidence and its independently verified integration.

## Companion startup and redraw regression — corrected

The September 5 recording exposed an acceptance gap: the native outlines and
guides vanished after overlay updates, and enabled Reporters could miss restored
tab attachment. Earlier tests counted redraw requests without verifying native
canvas retention. Both companions now wake on deferred controller/document/tab
attachment, resolve a single restored text selection, and invalidate the current
native canvas after publication instead of broadcasting `Glyphs.redraw()`.
Drawing restores Cocoa graphics state, and same-layer curve updates retain the
last completed comb while its replacement is calculated. The reference keeps
its existing 150 ms quiet interval and held-mouse guard.

Added restored-startup, text-mode, attachment coalescing, retained-cache,
atomic-publication, and graphics-state regression coverage. Bundle tests now
verify identical shared SDK copies in the bridge and both companions, and match
the installed entry-point source. The full suite passed with 2,091 tests and
5 skips; the final focused lifecycle/build run passed 49 tests. The reproducible
native check loads both built entry points against Glyphs 4.0.1 (4004), verifies
their Cocoa selectors and native-outline flags, and accepts native view
invalidation. See `src/companions/TESTING.md` and
`build/companions-native-acceptance.json`.

The final bridge and companion bundles were installed and Glyphs restarted.
In the sole disposable Dactylotype copy, the comb appeared on reopening; with
both Reporters enabled before a subsequent restart, the reference loaded and
displayed “Last Saved · No changes” without touching the canvas or toggling a
Reporter. Five successive native nudges, a node drag, and their native Undos
retained outlines, guides, and both overlays after updates without panning.
The comparison label changed after edits and returned to “No changes” on Undo.
These are observed editor checks, separate from the headless native gate.

All test edits were undone and saved. Every disposable file matched the saved
reproduction backup byte-for-byte, and the original source hash stayed unchanged.
Screenshots and the preservation record are in `build/companions-redraw-live.json`.
Repeated runtime builds and `git diff --check` passed. The server-window redesign
and reference-menu indicators remain in the installed build.

## Milestone 6 packaging

The accepted workflows now share the 0.001 font-unit preparation/comparison
tolerance. This does not change exact restoration or native history. Packaging
adds private arm64/x86_64 runtimes, transactional component installation and the
first-launch placeholder. See `V2-SIMPLE-RESET.md` and the local acceptance
report; visible Glyphs verification remains distinct from detached native tests.
