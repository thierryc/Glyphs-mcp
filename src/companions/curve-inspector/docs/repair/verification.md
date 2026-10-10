# Verification and qualification

> **0.5.0 human-workflow update:** one fixed 280 × 146-point panel contains
> Star / Default node, Max change in font units, All masters and Apply. No
> preview, disclosure area or separate Tunni control. Native detached repair is
> accepted only within the effective-outline limit, including combined edits.
> Star changes broken joins only; Default node materializes native repair and
> resolves existing curve/curve stars. Tunni is enabled internally and retained
> only after the same validation. All masters accepts corresponding repairs
> together; this establishes edited-master evidence, not interpolation coverage.
> Original proposal/designspace interfaces below remain available to agents.
> See the [companion README](../../README.md) for the current human workflow.



**Status:** this is the repair acceptance contract. Analytic/unit tests and
independent Glyphs 4.1.1 build 4108 trials now exist in `qualification/` in the
companion. Those records cover ordinary masters, two axes/four masters, an
intermediate layer, conditional selection and boundaries, actual application
and exact fixture reset. Installed UI and broader/export cases remain gates.
Cases below are requirements, not a claim that every listed case passed.

## Three distinct kinds of evidence

1. **Pure geometry:** derivatives, regularity, continuity and a continuous
   deviation bound for corresponding cubics.
2. **Native behavior:** exact connection edits, effective outlines, detached
   copies, caches and interpolation on a named Glyphs build.
3. **Designspace coverage:** finite locations and families evaluated with the
   native model. This is sampled evidence, not a continuous designspace proof.

Never substitute one for another. Stored-coordinate invariance does not imply
effective-outline invariance; smooth flags do not prove G1/G2; sampled shape
distances do not replace the cubic deviation bound.

## Pure engine fixtures

Use exact analytic controls, independently calculated expectations and seeded
adversarial examples. Normalize and repeat scale/translation/orientation cases.

| Case | Expected result |
| --- | --- |
| Exact G2, positive nonzero tangent | Accept diagnostic; repair is a no-op |
| Broken G1 | Detect direction mismatch; star requires native trial; handle method must qualify alignment or refuse |
| Opposite tangent directions | Fail oriented G1 |
| Equal curvature magnitudes, opposite signs | Fail G2; refuse impossible fixed-tangent candidate |
| Straight regular limits | Distinguish defined zero curvature from degeneracy |
| Interior inflection | Preserve permitted inflection; do not equate it with a cusp |
| Zero endpoint handle | Undefined endpoint curvature; no extraction in v1 |
| Interior cusp or possible zero-speed interval | Detect or refuse unresolved regularity |
| Parallel/nearly parallel tangent intersections | Refuse unbounded or unreliable candidates |
| NaN/infinite inputs | Reject before computation |
| Tiny same-sign curvature numerators | Diagnose conditioning; no unchecked square root/ratio |
| Candidate beyond tolerance | Refuse even if exact G2 |
| Adjacent isolated repairs that conflict jointly | Reject dependency block or find a separately validated combined candidate |
| Deliberate corner / locked target | Preserve state; explicit exclusion/refusal |
| Repeated repair | Stable no-op with no coordinate drift |

Reference pair in font units:

```text
left:  (-200,100), (-100,40), (-40,0), (0,0)
right: (0,0), (20,0), (100,40), (200,100)
```

Its unit tangent is (1,0). Curvatures at the join are 1/60 and 1/15 per unit.
Equalizing both handle lengths to 30 gives 80/2700 per unit on both sides.
Each changed handle moves 10 units; its exact segment deviation is 40/9 units.
At UPM=1000, that exceeds the default 1-unit limit and must be refused despite
G2 success. This is an analytic example, not a claim about native star output
or the precise SuperTool candidate for these controls.

Changing the original outgoing length to 39 permits a reference equal-length
candidate of 39.5: each changed handle moves 0.5 unit, with exact deviation
2/9 unit. This verifies the bound calculation; acceptance still requires all
other checks. Equal original lengths of 40 give an exact G2 no-op. Changing
the right outer handle to (100,-40) gives opposite curvature signs and no
positive fixed-tangent G2 length solution.

Test the integral matrix against independent polynomial integration. Test
subdivision invariance and upper-bound conservatism against exact one-handle
maxima, endpoint changes and multi-control changes. Dense samples can catch
bugs in bounds but cannot prove the bound by themselves. Exercise numerical
error margins and exhausted subdivision budgets.

Compare the pure SuperTool adaptation against pinned source behavior for its
valid domain, separately from the full upstream command's balancing sequence.
Refusals added by this project need explicit fixtures. Avoid tests that merely
recalculate the implementation formula without independent expectations.

## Native star qualification gate

On disposable fonts, record Glyphs version/build, macOS, Python wrapper revision,
engine revision and fixture identifiers. Establish:

- The exact connection getter/setter and `GSSUPERSMOOTH` behavior on the host.
- Stored coordinates before and after a star trial.
- The native effective outline, including the effective join and every affected
  primitive segment.
- Representation type, closed state, orientation, segment mapping and control
  coordinates of `primitiveRepresentation` or the qualified alternative.
- That detached trial computation does not mutate, open, save or dirty the source
  document beyond the known workflow-wrapper behavior.
- Cache freshness after connection-only edits, coordinate edits and native
  interpolation; independent repeats produce the same result within policy.
- Exact preservation of relevant HOI and special-layer attributes in copies.
- Neighboring-join behavior and interaction between adjacent star nodes.

Do not use destructive special-to-Bézier conversion on live source paths for
inspection. A conversion on a detached copy still requires proof that it
represents the native effective outline, with verified correspondence.

If extraction or mapping is ambiguous, stars remain unavailable for accepted
repair. Report `native_unqualified` or `incompatible_correspondence`. Do not
fall back silently to raw cubic coordinates.

Curve-to-line raindrop behavior and zero handles are negative fixtures for v1:
the adapter recognizes them and refuses them without topology changes.

Version 0.3.0 supersedes the raindrop exclusion: line/curve and curve/line have
dedicated expanded-native-chain checks. Zero handles remain unsupported. Test
both directions, open/closed paths and implicit closing lines; generated internal
G1 joins are distinct from requested G2 joins. Qualify short-line refusal,
native segment omission, drawing-grid quantization, adjacent transitions and
master-family correspondence. Native records are independent of installed UI
qualification and retain source preservation, application and repeat-no-op evidence.

## General-master family model

Preserve the complete native font model. Partition evaluation by compatible
topology and substitution family; identify the ordinary master family, brace or
intermediate layers, bracket/alternate families, and supported special layers.
Families that cannot be mapped must be listed as unsupported, not omitted.

Resolve axis order/IDs, master locations, configured static instances and native
interpolation parameters. Use native interpolated fonts per location rather than
hand-coded linear interpolation. `GSInstance.interpolatedFont` is documented,
but detached setup and axis assignment still require host qualification.

Repairs may coordinate edits across all relevant family layers. Independent
master success is insufficient. A changed layer in a compatibility family must
not cause an unplanned incompatible family or lose special-layer semantics.
If components are outside the declared implementation, report them as uncovered;
never treat the Reporter's omitted components as repaired.

## Sampling contract

The request declares an axis region and families before trial/application.
For each native interpolation cell in the region, evaluate the union of:

- Every contributing master and special/intermediate source layer.
- Configured instances whose locations lie in the declared region.
- Special-layer substitution boundaries, the boundary itself and representable
  points on both sides using a recorded axis-scaled epsilon.
- A Cartesian five-position lattice per varying axis: normalized cell positions
  0, 0.25, 0.5, 0.75 and 1.
- An independent Cartesian interleaved set: 0.125, 0.375, 0.625 and 0.875 per
  varying axis, plus boundary-adjacent probes where required.

Evaluate families separately when they share a location. Count the union of
distinct locations before any trial edit; also report family-location evaluation
count. The cap is **4096 unique locations per proposal**, and an implementation
may need an additional declared work budget for many families. Fixed axes do
not multiply the lattice. Deduplicate only truly identical native locations,
not nearby locations rounded for convenience.

Examples of lattice growth before other mandatory probes:

| Varying axes, one cell | Five-position locations | Interleaved locations | Total before overlap/probes |
| --- | ---: | ---: | ---: |
| 1 | 5 | 4 | 9 |
| 2 | 25 | 16 | 41 |
| 4 | 625 | 256 | 881 |
| 5 | 3125 | 1024 | 4149 |

Even a single five-axis cell exceeds the cap with this independent set. Return
`location_budget_exceeded` and a concrete proposed narrower region. Narrowing
is an explicit scope decision, not silent truncation or automatic approval.
Additive masters, more cells and boundaries can exceed the cap sooner.

Each location checks native effective outline regularity, G1/G2 at affected
joins and their neighbors, and continuous per-pair shape bounds. Baseline and
trial use the same location and family. Record expected/evaluated locations,
missing locations, family coverage, failed joins, maxima and bound confidence.
An early failure may abort remaining work, but the remaining coverage is then
reported as incomplete.

Sampling establishes evidence only in the stated region. A proposal verified
in a narrowed region must not claim whole-designspace verification. Continuous
per-cubic deviation bounds do not extend automatically between designspace
locations or across substitution boundaries.

## Guard and recovery fixtures

Test coordinate-only, exact-connection-only, HOI-only, lock, topology, layer-family,
axis and master-location changes between preview and apply. Every applicable
change must invalidate the old proposal. Test identical coordinates in a different
document, wrong owning layer, background mistaken for foreground, and document
replacement after restoration.

Test partial native failure, job timeout and repeated dispatch. Verify that an
existing job is reconciled rather than replayed. On disposable fonts, demonstrate
whole-font saved-baseline restoration and its loss of later unsaved changes.
Do not label that test as selective outline rollback. Test narrow exception
compensation separately if implemented, including a conflicting later edit that
must prevent compensation.

## UI and Reporter regression checks

Preserve and rerun the existing companion, curve-lifecycle and build checks.
Use disposable native/UI trials for:

- Opening the repair controller with the overlay disabled.
- Reporter enable/disable and document/tab restoration without font edits.
- Preview cancellation with zero source mutation.
- Document switching and stale background results.
- Coordinate, connection and HOI edits invalidating previews and cached effective
  geometry.
- Context-menu targeting of the selected joins and correct surface.
- Apply with an unchanged proposal, then actual native verification.
- Failed/refused/incomplete coverage states without an enabled successful Apply.
- Existing comb limits, coalescing, graphics state and active-view invalidation.

Do not add broad runtime changes to make these checks pass. Keep repair execution
outside drawing and refresh paths.

## Release evidence

Each qualification record contains host/build versions, source and engine
digests, fixture inputs, exact methods and tolerances, native extraction version,
requested/evaluated region and families, before/after metrics, failures, recovery
observations and human visual review. Make records reproducible on disposable
fonts and distinguish sampled checks from analytic bounds.

Visual review evaluates whether the bounded change preserves the intended
design; it does not replace mathematics. Export behavior is a separate gate:
native editor evidence is not proof that every export format preserves star
semantics or produces identical outlines.
