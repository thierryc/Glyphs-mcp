# Pen-point distribution and cleanup

Use this mode for pressure/stroke controls, crowded interior points and master
profile mismatches. It is distinct from closed-seam normalization. The goal is
few meaningful controls describing the intended stroke, with stable editing and
interpolation. A uniformly spaced set is not inherently cleaner.

## Establish scope and intent

Discover the current live document and exact glyphs/ordinary master layers.
Use a clearly named live duplicate for trials, including unsaved edits. Keep
private fonts, measurements and drawings local. Do not save or alter the owner's
source as a prerequisite for experimentation.

Choose exact preservation or explicitly authorized bounded changes. If the
request permits small changes without a numerical budget, state a conservative
trial budget before testing and report achieved errors. A budget is a maximum,
not permission to redesign thickness, contrast, rhythm or pressure peaks.

Capture full geometry, path attributes, all Pen-point fields and stored defaults.
Address each control by glyph/layer/path/incoming-end-node/control index and t.
Include width, height, angle, placement, progression and locks. Native inherited
sentinels are valid. Use authored `position`, never `positionPrecise`.

## Diagnose before simplifying

- Check finite valid values, t ordering, repeated times and unsupported metadata.
- Measure spacing along the same traversed stroke, approximately by arc length;
  spatially coincident strokes or open returns are separate addresses.
- Report close controls as suspicious. They can encode intentional sharp changes.
- Protect stroke endpoints, deliberate pressure/contrast extrema, corners, caps,
  angle/placement changes, custom easing and explicit user pins. Do not require
  a Pen point at every Bézier node.
- Preserve inactive open-start controls unless their removal is separately
  requested and qualified. Corner smoothness, path direction and fill are outside
  this cleanup.
- Compare master profiles independently of native `compareString`: compatible
  outlines can still have different Pen-point counts or ownership addresses.
  Equal total counts also do not establish correspondence. Corresponding t
  values may legitimately differ; do not snap them to a common grid blindly.

## First repair correspondence, then simplify

If profile slots differ across masters, the existing native intermediate shapes
may already be wrong. Do not use those intermediates as an unquestioned reference
or silently treat large differences as successful small-change cleanup. Trial
the least disruptive alignment: remove a redundant extra control OR add a
shape-neutral corresponding control. Bound changes to each authored master,
validate the resulting native profile interpolation, and separately report and
visually review intermediate changes. A control measured from a normal-section
intersection is only a starting estimate; native expansion must qualify it.
Once correspondence is sound, freeze that approved baseline for simplification.
Report both the original-to-final change and the aligned-reference-to-final
change. A small number in the latter comparison does not bound the former.
For a previously mismatched designspace, check generated profile values against
the intended corresponding master controls and the native interpolation
coefficients; a valid native shape alone does not prove correct correspondence.

## Preferred simplification: joint adaptive knot removal

1. Retain the centerline, node identities/order and path attributes exactly.
   Treat meaningful stroke transitions as protected profile knots.
2. Build corresponding control slots across all masters. A missing control is a
   mismatch to investigate, not a reason to insert a fabricated default.
3. Rank removable *groups* by low profile variation and crowding measured in
   normalized arc length. Ramer–Douglas–Peucker-style scoring can seed candidates;
   it cannot validate Glyphs' native progression or inherited values.
4. Trial a group on detached native copies. Use Glyphs' stroke expansion to
   evaluate its actual effect. Compare every separate stroke in every master and
   native intermediate instances on each affected designspace interval. Preserve
   caps, joins, counter topology, overlap relationships and contour winding.
5. Score the worst normalized error over all masters, instances and required
   metrics. Never average away a failing master. Measure boundary deviation and
   explicit profile changes; include width/height, angle, placement and progression
   where evaluation is available. If only native boundary evidence is available,
   disclose that limit and keep every surviving control unchanged.
6. Remove the least consequential qualified group, then re-evaluate. Always
   compare cumulative changes against the ORIGINAL, preventing accumulated drift.
   Stop when no group passes. This greedy method is a practical strategy, not a
   proof of a globally minimal control set or perceptual perfection.

An extra near-boundary control in only some masters can sometimes be removed
from those masters to match an existing simpler layout. Evaluate the joint
result. If removal changes the stroke too much, hold it; adding a control with
correct evaluated values is a separate repair requiring native qualification.
Do not arbitrarily move endpoints or spread controls evenly to improve a count.

For difficult cases, a joint constrained profile fit with a sparsity penalty can
propose fewer knots. Lock required extrema/endpoints and shared slot identities;
keep the same native worst-case validation. Avoid fitting a substitute linear
width model when the native stroke depends on easing, angle or anisotropy.

## Mechanics and verification

Interior Pen-point cleanup is not currently a typed outline operation. For an
explicitly authorized custom font edit, use the existing
[native script workflow](https://github.com/thierryc/Glyphs-mcp/blob/main/skills/glyphs/references/python-scripts.md) from `$glyphs` with
`script.native.v1`, preparation v3 and `script.recovery.snapshot.v1`. It supports
dirty/pathless fonts and pre-run whole-font memory recovery. It does not inherit
typed selective Undo. Never bypass rejected writes, stale guards or locks.

Reuse native attribute access/snapshots; avoid wrapper attribute setters that
can round floats. Qualify native expansion on detached generic originals first;
verify its baseline matches live expansion and does not change the live object.
`expandedStroke` was observed on Glyphs 4.2 (4202); other hosts need qualification.
Never expand the editable live stroke merely to measure it.

Preflight ALL targets and expected full state before the first live write.
Apply exact approved control-array edits as one recoverable script; copy surviving
Pen points and preserve their explicit/inherited storage. Hold hints, references,
locks, incompatible layouts and unsupported settings with actionable reasons.
Native batching should yield between bounded layer/glyph callbacks.

Afterwards verify centerlines and non-target data exactly, intended control
addresses/count/order, full surviving profiles/defaults, native master
compatibility AND profile correspondence, intermediate instances, and native
expanded outlines. Check at editing and text scales; numerical similarity alone
does not establish nicer lettering. Offer recovery, leave the trial unsaved,
and rerun the same strategy: no further qualified change should remain.

## Measurement helper and native controls

[`../scripts/pen_point_strategy.py`](../scripts/pen_point_strategy.py) contains
font-independent boundary measurements and deterministic best-first selection.
It never edits or saves a font. Supply native expanded outlines and explicit
required validation cases. Boundary results distinguish sampled error from a
conservative sampling/flattening upper bound. Compare separate strokes rather
than a merged silhouette that can hide overlap errors. Contour topology/winding
checks do not prove preservation of every intersection; inspect overlaps too.

The [official Glyphs handbook](https://handbook.glyphsapp.com/strokes/#pen-points)
documents adding controls from a stroked path's context menu, deleting interior
Pen points, and clearing node-attached Pen-point fields in the Info box while
retaining the outline node. It also documents progression and the special effect
of a single Pen point on a closed stroke. These native controls do not establish
that an automatic simplification is safe.
