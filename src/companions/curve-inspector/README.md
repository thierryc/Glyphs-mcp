# Glyphs Curve Inspector

An independent Reporter for the currently visible layer. It copies at most 128
cubic drawing segments on the Glyphs main thread, builds a bounded signed-curvature
comb and connected endpoint envelopes in one background worker with
latest-refresh-wins behavior, and draws only cached paths. Its sampling,
colors, alpha, scale and zoom-dependent line widths match the previous working
Glyphs MCP Curvature display. Unchanged UI notifications are coalesced. The
pure `curve_core` package is also bundled with the sidecar for external jobs.

Enabling the Reporter schedules an initial refresh on the next Cocoa main-loop
turn, so the overlay appears without a canvas interaction. Re-enabling also
redraws unchanged cached geometry. Disabling invalidates pending worker results.

Restored documents and tabs also wake the Reporter after controller attachment,
including a single selected layer in text mode. Same-layer edits retain the last
completed comb until the next result is ready. Publication invalidates only the
native canvas, and drawing restores Cocoa graphics state. See [regression gates](../TESTING.md).

## Inspect & Repair

Curve Inspector 0.5.1 uses one fixed **280 × 146 point** floating panel.
Open **Edit → Inspect & Repair…**, including while the Reporter is disabled.
The Reporter remains visualization-only.

Choose **Star** (initially selected) or **Default node**, set **Max change** in
font units if needed, optionally enable **All masters**, then click **Apply**.
The default limit is `0.001 × UPM`: 1 unit at 1000 UPM. Switching fonts resets
that default. Invalid, zero, negative and non-finite inputs disable Apply.
There is no preview, scope menu, Tunni control, disclosure area or resizing.

Scope is captured afresh at Apply:

- Font tab: selected glyphs, or the whole font if none are selected.
- Edit view: selected nodes/handles/paths, or all eligible joins in the current
  glyph if nothing is selected. Selecting a curve handle includes its complete
  curve and both eligible adjoining joins. Unselected intentional corners and
  locked targets are preserved.
- All masters: corresponding ordinary master contours must all pass before a
  repair is accepted. Healthy masters can remain unchanged. Backup and special
  layers are excluded; this checks edited masters, without interpolation coverage.
- Otherwise only the current layer/master is targeted. The visible background
  is respected; missing corresponding backgrounds are refused.

**Star** diagnoses native continuity and converts only joins needing G1/G2
repair. Healthy ordinary nodes and existing stars remain unchanged. Native
curve/curve stars and line/curve raindrops preserve stored coordinates while
changing the effective outline.

**Default node** trials native star repair on detached geometry, then stores its
effective node and handle coordinates with a regular smooth connection. It also
resolves existing curve/curve stars, even when they are already G2. Healthy
ordinary joins remain unchanged. Tunni balancing is enabled internally for
cubics. It is accepted only if continuity, neighboring joins and the outline
limit pass; otherwise the measured native repair is retained. Straight/curve
joins align existing controls without inserting nodes. Materializing an expanded
raindrop into regular nodes remains unsupported.

Both modes enforce **Max change on the effective outline**, including native
movement, conversion, balancing and the combined contour result. Construction
and normal native drawing are checked separately. Native grid quantization can
make a star-to-regular conversion visibly differ even though its unrounded
geometry matches; a tight limit correctly refuses that change. Continuous
Bernstein/subdivision bounds and native-chain correspondence come from the
shared engine. Excessive or unresolved bounds are rejected; fallback never
bypasses the limit. Independent bounded repairs may proceed when other joins
are refused, while every accepted cumulative result is checked against the
original contour and all corresponding masters.

Detached calculation precedes guarded application. Exact coordinates,
connections, attributes, ownership and foreground/background identity are
checked; expanded corner/cap/brush hints and stroke contours remain unqualified.
Apply groups native Undo once per changed glyph, verifies the actual result and
never saves. A failure compensates the affected writes; previously completed
glyphs remain undoable if the panel closes or the document changes. The result
reports repaired, converted, already-smooth, limit-rejected and unsupported
counts. Hover over it for detailed reasons and the certified outline bound.

The advanced shared `NativeAdapter` interfaces remain available for agent
analysis/proposals and master-family sampling. An agent preview-only request
remains non-mutating. The 0.5.1 release retains the exact qualified 0.5.0 engine.
[Release qualification](qualification/release-0.5.1.json) distinguishes carried
forward behavior evidence from final signed-byte checks and native load status.
The [candidate status](qualification/candidate-status.json) tracks installation.
Historical detailed QA records remain local; they are not public release assets.

Inspection, repair engine, native controller and agent skill belong to this
companion in the existing Glyphs MCP repository. The [repair documentation](docs/repair/README.md)
records the mathematics, source/license comparisons, architecture and gates.
Build the plugin and bundled skill with `python3 scripts/build_curve_inspector.py`.
Both carry the same engine/geometry digest, Apache notices and pinned SuperTool
revision. Skill source lives under `skill/glyphs-curve-repair/`; managed/global
registration awaits a release with an immutable source commit.

Native 0.5.0 qualification on Glyphs 4.1.1 build 4108 covered both modes,
selected handles, outline bounds, atomic master refusal, adjacent joins, document
switching, disabled overlays and per-glyph Undo. The independent adapter's
ordinary, multi-axis and conditional-family records provide sampled evidence
within their qualified scopes. Manual/variable instances, unclassified special
layers and export equivalence remain explicit gates. This signing patch carries
forward unchanged behavior; it does not claim new platform or interpolation
coverage. The previous verified 0.4.0 and 0.5.0 bundles are retained locally.

Standalone distribution follows [RELEASING.md](RELEASING.md). Version 0.5.1 is a
packaging/signing patch over the natively qualified 0.5.0 code. Its release assets
and local tag are independent of the desktop app and Sparkle update feed.

The 0.5.2 candidate keeps the fixed panel and repair behavior. When no outline changes, the status explains whether joins are already smooth, the change limit blocked repair, the selection is locked/unsupported, or no eligible joins were found. Full counts and reasons remain in the tooltip.
