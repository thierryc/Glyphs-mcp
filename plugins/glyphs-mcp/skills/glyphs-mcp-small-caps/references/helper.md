# Native helper and recovery

Load `scripts/derive_caps.py` as the `source` of an existing native Python job,
`entrypoint="script"`, with `targets:[]` for this coordinated glyph-creation task.
The outer job supplies the exact live font; never evaluate against `Glyphs.font`
or current selection. Its native script recovery must be negotiated separately.
Set `auto_keep=false` while waiting for designer review. No saved source is needed.

## Closed request

`run_caps(font, params, api=None)` supports only `inspect`, `construct`, `verify`.
Create, continue, refine and audit are workflow modes, not accepted `stage` values.
Importing it has no side effects or Glyphs dependency. Example initial inspection:

```json
{
  "stage": "inspect",
  "masters": ["EXACT_MASTER_ID"],
  "rows": [{"source": "H", "kind": "sc"}, {"source": "H", "kind": "pc"}],
  "sets": {
    "sc": {"EXACT_MASTER_ID": {"height": 550, "scaleX": 0.84, "offsetX": 0, "offsetY": 0, "tracking": 5}},
    "pc": {"EXACT_MASTER_ID": {"height": 500, "scaleX": 0.81, "offsetX": 0, "offsetY": 0, "tracking": 6}}
  }
}
```

These numbers illustrate the interface, not design defaults. `height`, offsets and
tracking use font units; `scaleX` is a positive factor. Supply all settings for
each constructed set/master. The agent resolves the petite x-height default or
approved override into an explicit `height`; the helper does not choose that
default. Review settings through the pilot within the recorded design constraints.
See [transform and measurement limits](#transform-and-measurement-limits).

Rows accept `source`, `kind` (`sc` or `pc`) and optional exact `destination` ending
in that suffix. `.smcp`/`.pcap` destinations are not accepted, even when explicit.
This restriction and the requirement for existing source glyphs apply to every
stage. For audits of other names or sets without usable sources, use ordinary
reads; do not rename glyphs or fabricate source mappings. Automatic naming uses
native character metadata, not lowercase string operations on glyph names.
Dotted I and sharp S have explicit mappings;
ambiguous names/alternates need a designer-reviewed destination. Alternate names
receive no Unicode assignments.

For construction, supply the inspection's `identity` as `identity` and its complete
`guards` as `expected`. The helper checks the font family/UPM/master metrics, source and
destination foregrounds, anchors, widths/keys and recursive component dependencies.
The outer job also binds the exact document. This is a defined geometry projection,
not a cryptographic guarantee of unchanged full-font metadata.

`componentMap` is optional, per kind, for example:

```json
{"sc": {"acutecomb.case": "acutecomb.sc"}, "pc": {"acutecomb.case": "acutecomb.pc"}}
```

Base mappings come from the rows. Mark variants must exist or be explicitly
included as source rows with reviewed destinations. Composite dependencies are
ordered before attachment; unresolved mappings and cycles reject construction.
Only automatically aligned pure composites are eligible. Manual placements, smart
components, mixed shapes, open/empty paths and incompatible source masters require
human construction. New composite anchors are generated after native alignment.
Marks themselves use the same explicit transform mechanism; their correct scale,
anchor placement and optical distance require review.

The helper copies requested foreground master layers only. New base hints, metrics
keys, backgrounds, guides and annotations are cleared; the source remains intact.
Existing derived glyphs are never regenerated, even with matching fingerprints;
construction also cannot fill missing or unfinished masters of an existing glyph.
Use explicit local outline corrections or separately scoped completion for
authorized revisions. Partial master coverage needs completion before export;
native default layers are not finished masters. The helper does not copy uppercase
kerning or create features.

For `verify`, provide the matching `identity` and last `resultGuards` as `expected`;
`changedSinceReview` compares those recorded fingerprints with current state. It
does not certify aesthetics or feature behavior. Without suitable prior evidence,
use fresh inspection and report unavailable historical comparisons. Reinspect
after accepting manual changes before further construction. An audit needs no
construction, duplicate or edit job; ordinary reads can supply its evidence.

## Transform and measurement limits

For outline sources the helper uses
`scaleY = (height - 2*offsetY) / master.capHeight`, translates vertically by
`offsetY`, then applies the qualified offset when either offset is nonzero. The
intended flat height and baseline assume source alignment at `capHeight` and zero,
and symmetric vertical expansion matching the offset. Inspect measured source
alignment and actual offset results before relying on those assumptions. There
is no measured-source-height, baseline, arbitrary vertical-scale or regional
compensation parameter. Do not alter global metrics to make the transform fit.
Resolve discrepancies through the [design procedure](design.md#height-and-weight-compensation)
and a separately scoped correction with recovery or designer handoff.

Existing source overshoot follows the transform and still needs optical review.
Tracking adds space to both sides; advance width includes horizontal offset and
tracking. Inspect actual ink bounds and sidebearings after compensation. Base
anchors are transformed with the copied layer; composite anchors are generated
after native alignment. Neither establishes approved mark placement automatically.

`construct` checks detached candidates internally, then attaches them in the same
call. It does not offer a detached-preview stage or a human review pause before
attachment. Qualify detached copies separately before construction and review
the resulting pilot before expansion.

Reported bounds cover the full layer. `topOvershoot` is its top bound minus the
supplied height and `bottomOvershoot` is the negative bottom bound; these fields
do not isolate base alignment, optical overshoot, accents, tails or descenders.
Supply the intended height when using those comparisons; without it the reporting
code uses zero. Read back native coordinates at documented operation-appropriate
precision and measure relevant regions independently. Numeric agreement alone
does not establish optical acceptance.

`mastersCompatible` compares ordered path closure/node-type sequences and component
names in the requested masters. It does not establish semantic node correspondence,
contour starts/directions or intermediate shape quality. Inspect those separately.
`changesVerified` records construction completion or agreement with supplied
verification fingerprints; it is not design acceptance. `interpolationVerified`
and `featureBehaviorVerified` remain false: this helper performs neither sampled
interpolation checks nor feature verification. Record external evidence separately.

## Offset Curve qualification

Zero offsets are always a clearly identified scale-only candidate. Nonzero offsets
require `offsetQualification` containing the exact string `build` and
`adapter:"layer-filter-keep"`. This records agent-observed qualification, not
an authenticated approval or an executable capability supplied by inventory.
This is the implemented adapter; no Core Offset Curve class-selector adapter is
provided by this helper.

Before supplying it, on a disposable fixture in that same Glyphs build:

1. Find the existing `GlyphsFilterOffsetCurve` instance in `Glyphs.filters`.
2. Confirm the layer-local `filter` method. Do not instantiate arbitrary classes
   or use font-wide `processFont_withArguments_` to approximate master targeting.
3. Apply `filter(layer, False, {0:dx, 1:dy, 2:0, 3:0.5, 4:'keep'})` to a copy.
4. Verify actual horizontal/vertical gains, flat height, baseline, stems, curved
   counters and joins, contour order/starts/directions and semantic correspondence,
   exact node types/order and fractional coordinates in every requested master.
   Confirm that testing copies preserved source fingerprints; nominal offsets
   and a Keep Compatible setting do not prove these properties.
5. Record measured results, host build and limits. Presence or a successful return
   alone does not qualify this adapter. The helper additionally rejects topology
   changes detectable by its structural comparison before attaching candidates.

If correspondence changes despite Keep Compatible, retain the pilot for designer
adjustment; do not accept that candidate or retry speculative corrections.

If unsupported or inaccurate, stop automation and open the exact native target:
**Filter → Offset Curve**, set reviewed Horizontal/Vertical values, turn **Make
Stroke off** and **Keep Compatible on**, preview, and ask for adjustment. Recheck
height, counters, fractions and interpolation afterward. Do not add an export
filter to obtain editable source outlines. RMX has no helper adapter in v1.

## Reports and failure

Results include schemaVersion, identity, rows, guards/resultGuards, per-master
bounds/widths/anchors/topology, created/preserved/skipped/needsReview, review data,
changedSinceReview when verifying, verification flags and nextActions. JSON reports
are separate from font metadata. `review` carries recorded approvals, manual
corrections, open issues and measured correction times supplied by the coworker.

Optional `reportPath` is a new absolute file in an existing task directory; writes
are create-only. No report overwrite, font save or export occurs. The caller can
instead save the returned report through its normal workspace tools.

All mappings, fingerprints, settings, candidate transforms and dependencies are
preflighted before attachment. A native attachment/alignment failure may still
leave partial edits: inspect and use the existing script's Restore before run;
never auto-reload or replay. Restoring replaces the whole pre-run font and later
edits, and clears Undo history. Report-file effects are outside that recovery.
