# Native helper and recovery

Load `scripts/derive_caps.py` as the `source` of an existing native Python job,
`entrypoint="script"`, with `targets:[]` for this coordinated glyph-creation task.
The outer job supplies the exact live font; never evaluate against `Glyphs.font`
or current selection. Its native script recovery must be negotiated separately.
Set `auto_keep=false` while waiting for designer review. No saved source is needed.

## Closed request

`run_caps(font, params, api=None)` supports `inspect`, `construct`, `verify`.
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
tracking use font units; `scaleX` is a positive factor. Choose all settings through
the pilot. Vertical scale is `(height - 2*offsetY) / capHeight`, with `offsetY`
translation restoring a flat baseline after symmetric offset. Existing source
overshoot follows the transform; read the measured overshoot and refine optically.
Tracking adds space to both sides. Width includes horizontal offset and tracking.

Rows accept `source`, `kind` (`sc` or `pc`) and optional exact `destination` ending
in that suffix. Automatic naming uses native character metadata, not lowercase
string operations on glyph names. Dotted I and sharp S have explicit mappings;
ambiguous names/alternates need a designer-reviewed destination. Alternate names
receive no Unicode assignments.

Supply the inspection's `identity` and complete `guards` as `expected` for
construction. The helper checks the font family/UPM/master metrics, source and
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
Existing derived glyphs are never regenerated, even with matching fingerprints.
Use explicit local outline corrections for authorized revisions. Partial master
coverage needs completion before export; native default layers are not finished
masters. The helper does not copy uppercase kerning or create features.

For `verify`, provide the last `resultGuards` as `expected`; `changedSinceReview`
identifies manual/source changes. It does not certify aesthetics or feature behavior.
Reinspect after accepting manual changes before further construction.

## Offset Curve qualification

Zero offsets are always a clearly identified scale-only candidate. Nonzero offsets
require `offsetQualification` containing the exact string `build` and
`adapter:"layer-filter-keep"`. This records agent-observed qualification, not
an authenticated approval or an executable capability supplied by inventory.

Before supplying it, on a disposable fixture in that same Glyphs build:

1. Find the existing `GlyphsFilterOffsetCurve` instance in `Glyphs.filters`.
2. Confirm the layer-local `filter` method. Do not instantiate arbitrary classes
   or use font-wide `processFont_withArguments_` to approximate master targeting.
3. Apply `filter(layer, False, {0:dx, 1:dy, 2:0, 3:0.5, 4:'keep'})` to a copy.
4. Verify flat height/stems, curved counters and joins, exact node types/order,
   fractional coordinates, source preservation and every requested master.
5. Record measured results, host build and limits. Presence or a successful return
   alone does not qualify this adapter. The helper additionally rejects topology
   changes before attaching candidates.

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
