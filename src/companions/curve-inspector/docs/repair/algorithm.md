# Geometry and repair policy

This document contains **derived mathematics**, **inspected upstream behavior**,
and **acceptance rules**. The engine is now implemented; independent host
evidence is in the companion's `qualification/` folder. Qualification is specific
to the recorded cases rather than every case in these research derivations.

## Cubics and regularity

For control points P0, P1, P2, P3, use the cubic Bernstein basis:

```text
B(t) = Σ[i=0..3] b_i³(t) P_i,             0 ≤ t ≤ 1
b_i³(t) = choose(3,i) t^i (1-t)^(3-i)
B'(t) = 3 Σ[i=0..2] b_i²(t) (P_(i+1)-P_i)
B''(t) = 6 [(1-t)(P2-2P1+P0) + t(P3-2P2+P1)]
B'''(t) = 6 (P3-3P2+3P1-P0)
κ(t) = det(B'(t), B''(t)) / ||B'(t)||³
```

Signed curvature is defined only at regular points, where speed is nonzero.
A zero handle at an endpoint makes this formula undefined there. Returning
zero would falsely classify a singular endpoint as a straight, regular join.
Report `undefined_curvature`, with location and reason.

Use normalized local coordinates: translate near the join and scale by UPM.
Keep original units for proposals. Numerical regularity thresholds must be
separate from artistic shape tolerance and tied to a documented error budget.
Use analytic polynomial candidates plus conservative interval checks for
possible zero-speed regions. Sampling alone cannot certify absence of cusps.
Unresolved intervals are refused in v1.

## G0, G1 and G2

For consecutive cubics A and C meeting at J:

- G0: the same endpoint J.
- G1: nonzero endpoint velocities have the same oriented direction; one is a
  **positive** multiple of the other. Opposite directions fail this condition.
- G2: G1 plus equal signed curvature at the join. Parametric C2 is stronger;
  its equal derivatives are not required for font-outline G2.
- Visual balance: a design judgment or handle-distribution convention, not
  equivalent to G2.
- Interpolation kink: continuity fails in an intermediate outline even when
  the master outlines look smooth. It requires evaluation of the interpolation
  model; a static repair does not establish its absence.

Compare tangent angle using `atan2(det(vL,vR), dot(vL,vR))`, with an explicit
positive-orientation check. Compare signed curvature, not its magnitude alone.
Near a straight limit, use an absolute error budget in addition to a relative
one; relative curvature error alone becomes meaningless near zero.

**Proposed diagnostic defaults for fixture qualification:** tangent mismatch
at most 1e-6 radians; curvature difference in em-normalized coordinates at most
`1e-6 + 1e-5 * max(abs(κL), abs(κR))`. These are numerical diagnostic thresholds,
not proven native tolerances. Native coordinate precision and scale tests must
qualify them before release. If the host cannot meet them, document and version
the policy change; never silently relax them during a repair.

## Fixed-join G2 derivation

Write the two cubics as:

```text
A = (P0, P1, P2, J)
C = (J, Q1, Q2, Q3)
P2 = J - a d
Q1 = J + b d
||d|| = 1, a > 0, b > 0
```

At the join the first derivatives are 3a d and 3b d. Substituting the endpoint
second derivatives into the curvature formula gives:

```text
nL = det(d, P1-J)
nR = det(d, Q2-J)
κL = 2 nL / (3 a²)
κR = 2 nR / (3 b²)
```

When nL and nR have the same nonzero sign, G2 requires:

```text
b/a = sqrt(nR/nL)
```

Consequences, with J, d, P1 and Q2 fixed:

- Opposite signs have no positive-length solution.
- One zero numerator and one nonzero numerator have no finite solution.
- Two zeros give zero join curvature for all positive lengths; interior
  singularities and inflections still need inspection.
- Tiny numerators make the ratio ill-conditioned; refuse unresolved cases.

This explains why handle balancing cannot serve as a universal repair. It also
provides exact test controls independent of any particular implementation.

An investigated closed-form alternative minimizes squared displacement of
the two handles for a chosen tangent d and ratio r:

```text
b = r a
a* = [d·(J-P2_old) + r d·(Q1_old-J)] / (1+r²)
```

This follows by differentiating a quadratic objective. Positive lengths and
shape bounds further constrain the feasible interval. It is **not the chosen
default implementation**, and it does not select a globally optimal tangent,
join, contour or native star. Retain it as a reference candidate and fixture
oracle rather than introduce a competing unqualified repair engine.

## Default: native super-smooth stars

**Researched fact:** Glyphs documents super-smooth star connections between
curves as native G2 behavior. Stored point coordinates remain available while
the effective join is adjusted. Curve-to-line super-smooth nodes have different
behavior and use the separately qualified expanded-chain policy below. See the
[Glyphs handbook](https://handbook.glyphsapp.com/editing-paths/#super-smooth-nodes).

**Proposed execution:**

1. Capture exact native source state and resolve the owning surface and family.
2. Copy the complete relevant font model into detached trial state.
3. Set the exact `GSSUPERSMOOTH` connection at the trial join. Do not toggle
   an unknown connection or assign only the `smooth` boolean.
4. Obtain the native effective primitive outline before and after the trial.
5. Establish correspondence, diagnose the resulting joins and bound effective
   outline displacement.
6. Record both stored-coordinate invariance and effective changes, including
   effective join displacement.

The Python wrapper inspected in the local SDK exposes `GSSUPERSMOOTH` (102).
Its `smooth=True` setter uses `GSSMOOTH`; it is not an exact-star setter.
Host compatibility must be checked, rather than relying on a hard-coded number
without the native constant.

**Researched API and subsequent qualification:** the
[GSPath API](https://docu.glyphsapp.com/Core/GlyphsCore/GSPath/) documents
`primitiveRepresentation`, `isPrimitive` and special-to-Bézier conversion.
On Glyphs 4.1.1 build 4108, `primitiveRepresentation()` retained stored star
coordinates, while the AppKit drawing path contained the shifted effective join.
The adapter matches drawing elements to source node roles, rejects changed
topology and validates non-star coordinates against the source or qualified
grid rounding. It does not use nearest-point fitting. The 4108 PyObjC selector
accepts one input index and returns element/points. Unsupported extraction or
correspondence still blocks acceptance.

Native G2 intent is not a shape bound, a global optimality result, or proof that
all adjacent joins and interpolated outlines remain acceptable.

## Explicit alternative: SuperTool harmonization

**Inspected source:** SuperTool revision
`ccc71ee39ef72c0c34267410d2b9ebee454ec98c`, file
`SuperTool/SuperTool+Harmonize.m`. The Apache-2.0 implementation uses the same
family of tangent-intersection ratios as other established Glyphs tools.

With the consecutive local points `(a1, a2, J, b1, b2)`, intersect lines
`a1–a2` and `b1–b2` at D. Its construction is:

```text
p0 = distance(a1,a2) / distance(a2,D)
p1 = distance(D,b1) / distance(b1,b2)
r = sqrt(p0*p1)
t = r/(r+1)
J_candidate = (1-t) a2 + t b1
translation = J - J_candidate
a2_new = a2 + translation
b1_new = b1 + translation
```

The stored join J stays fixed. The upstream command also balances before and
after harmonization. This project separates the harmonization computation from
that command sequencing; optional balancing stays explicit and off by default.
Record this adaptation so it is not presented as identical full-command output.

**Proposed adaptation:** retain the inspected computation and attribution in a
pure Python function. Independently implement basic line intersection and vector
helpers; do not copy separately unverified submodule code. Add finite-value,
parallel-line, positive-length, curvature-sign and denominator checks. Compute
actual G1/G2 diagnostics from the final coordinates rather than infer success
from the formula or the node's smooth flag.

The upstream smooth-node precondition does not prove geometric G1. In particular,
translating handles does not generally align an arbitrary broken tangent. A
candidate failing G1 is refused. The explicit handle route now uses an oriented
unit-tangent bisector before the pinned computation for broken G1. Opposite
tangents are refused; final G2, bounds and neighbor checks remain mandatory.
This is an identified adaptation with analytic fixtures, not extra behavior
attributed to the upstream command.

GreenHarmony uses the same style of construction but moves J. GreyHarmony
translates handles while fixing J. Both are useful independent comparisons;
SuperTool is the pinned adaptation source. See
[sources and licenses](sources-and-licenses.md) for exact revisions and limits.

## Optional Tunni balancing

**Inspected source:** `SuperTool/SuperTool+TunniEditing.m` at the same revision.
For a cubic with endpoint-tangent intersection T:

```text
x = distance(P0,P1) / distance(P0,T)
y = distance(P2,P3) / distance(P3,T)
q = (x+y)/2
P1_new = (1-q) P0 + q T
P2_new = (1-q) P3 + q T
```

The source has early returns for certain nonpositive/large/tiny percentages.
These are heuristics, not an exhaustive mathematical classification of
inflections or degeneracies. Adapt them with explicit reason codes and stronger
regularity guards. Nearly parallel tangent lines require refusal when the
intersection is not reliably bounded.

Balancing is disabled by default. If enabled, compare the full final outline
against the original baseline and recheck all affected joins. Equal percentages
inside one segment do not imply equal curvature at either endpoint. Do not
accept a candidate merely because Tunni balancing completed.

## Shape measurement and continuous deviation bound

**Qualified grid behavior:** on 4108, restoring a layer's precision flag preserves
stored fractional coordinates but can round ordinary drawing controls. The
engine checks normal post-restoration drawings. For handles, it considers at
most 16 floor/ceil pairs around the SuperTool candidate, retains G2 candidates,
and orders them by the exact integral against the original. The on-curve stays
fixed; final native checks and shape bounds remain mandatory. Font grid settings
are never changed. No feasible nearby candidate means refusal, not relaxation.

**Proposed default:** maximum deviation ε = 0.001 em, equivalent to
`0.001 * UPM` font units. Measure effective-to-effective curves for stars and
baseline-to-final curves for coordinate repairs. A mixed method still uses the
original effective outline as its baseline.

For corresponding cubic control points, define ΔP_i = P_i_after - P_i_before
and ΔB(t) = Σ b_i³(t) ΔP_i. The integrated squared difference is exactly:

```text
E = ∫[0..1] ||ΔB(t)||² dt
  = Σ[i,j=0..3] dot(ΔP_i,ΔP_j) M_ij
M_ij = choose(3,i) choose(3,j) / [7 choose(6,i+j)]
```

The matrix follows by integrating the Bernstein products. E is a useful
candidate score in squared units; summing it across segments is not an
arc-length-weighted perceptual metric. It is not the maximum-deviation test.
With only one interior handle changed, `E = (3/35) ||ΔP||²`.

Because Bernstein basis functions are nonnegative and sum to one:

```text
max_t ||ΔB(t)|| ≤ max_i ||ΔP_i||
```

Subdivide the difference cubic with de Casteljau and compute this upper bound
on each leaf. The maximum leaf bound remains a continuous upper bound on the
whole parameter interval. Point evaluations supply lower bounds. Accept only
when an upper bound, including the numerical error allowance, is ≤ ε. Reject
when a trustworthy lower bound exceeds ε. Continue subdivision when undecided;
at the depth/work limit return `unresolved_deviation`, not acceptance.

For one changed interior handle, the exact maximum is `4/9 * ||ΔP||`, attained
at t=1/3 for the first handle or t=2/3 for the second. Use this as a bound test.

This is a bound between corresponding parameter values. It implies a
conservative geometric/Hausdorff upper bound for that pair, but is not the exact
Hausdorff distance. Neither the score nor the bound establishes a global optimum.

**Correspondence gate:** pair segments only when topology, orientation, endpoint
identity and parameterization are established. If a native conversion splits a
segment, use a validated common subdivision with mapped parameters; do not
match by array index or nearest sample alone. Unsupported conversion or changed
topology produces incomplete coverage/refusal. Stars may change both endpoints
and controls, so the general bound must be used rather than a handle-only bound.

## Deliberate features and interacting repairs

Preserve sharp corners and locked targets. Treat undefined curvature, incompatible
correspondence, sign conflicts, unresolved degeneracy, excess deviation and
neighbor regressions as explicit refusals. A mathematically smooth result can
still erase a deliberate design feature; diagnosis cannot silently authorize it.

Build dependency blocks from selected joins and the segments whose geometry they
can influence. Generate candidates against the same immutable baseline, then
trial the complete block. Recheck selected joins, adjacent joins, regularity and
deviation against the original. An already acceptable adjacent join must remain
acceptable. An already failing neighbor must not worsen beyond the documented
numerical comparison budget. If no feasible combined candidate is established,
refuse the block; do not greedily apply each successful isolated repair.

A repeat on unchanged accepted geometry must produce a no-op. Fingerprints and
engine version identify the baseline; an old preview is never silently reused
after a connection-only edit or HOI change.

## Interpolation and HOI

Under simple linear interpolation, a common positive incoming/outgoing handle
ratio across contributing layers is sufficient for G1 while the interpolated
handles remain nonzero. Different ratios can create intermediate kinks even
when both masters are G1. G2 involves nonlinear curvature ratios and does not
follow simply from G2 masters. Native special layers and HOI further change the
model, so use Glyphs' interpolation rather than replace it with this illustration.

HOI addresses interpolation trajectories, including effective intermediate join
positions. Keep it separate from native star repair and fixed-join harmonization.
The existing `dekink-native` domain is one axis and two ordinary masters with
compatible closed line/cubic paths; generalizing it requires new qualification.

## Explicit limits

No global optimizer, G3 claim, zero-handle extraction, topology change,
curve-to-line super-smooth transition, or continuous designspace proof is offered
by v1. These limits must be visible in diagnostics and operation results.

## 0.3.0: native line/curve transitions

The selected source node resolves both adjoining segments by path order. Lines
are represented analytically as exact degree-elevated cubics for diagnostics;
no handles or nodes are added to the stored source path. Native `GSSUPERSMOOTH`
trials use stars for curve/curve and raindrops for line/curve or curve/line.
Closed paths account for both explicit and AppKit implicit closing lines.

The native drawing is parsed in source segment order. A qualified raindrop adds
one cubic at its line-adjacent end of a source curve. Native line clipping must
remain inside the original straight segment and preserve its direction.
Missing, reordered or unqualified expansions are refused; no nearest fitting
or destructive conversion is used to infer correspondence.

Expanded chains do not have the old one-to-one cubic parameter correspondence.
Each native cubic is subdivided until its Bernstein control-polygon difference
from the degree-elevated endpoint chord is bounded by epsilon = tolerance/64.
The resulting polylines are matched by normalized chord arc length. Their
difference is piecewise linear on the union of breakpoints; the maximum endpoint
distance plus both flattening errors bounds all corresponding points and hence
bidirectional geometric distance. Budget exhaustion or an excessive upper bound
refuses the proposal. The bound may be conservative. The exact corresponding-
cubic integral is null for these chains, rather than fabricated across a split.

Continuity is diagnosed on the detached unrounded native construction; temporary
precision flags are restored before measuring the actual grid-rounded drawing.
Both constructions must pass continuous deviation bounds. Requested source
joins must reach G2. Generated internal joins must be G1; native 4108 fixtures
show that they are not necessarily G2. Drawing-grid continuity is reported
separately. Existing generated joins and neighboring source joins must not
regress. No global G2 claim is made for the entire generated transition.

SuperTool handle repair remains curve/curve only. An explicit line/curve handle
request receives `unsupported_method`, with native super-smooth as the supported
choice. Mixed selections with blocked targets report counts and locations and
remain non-applicable until the user changes the requested scope.

Mathematical references:
[Bézier continuity notes](https://people.kth.se/~weinkauf/notes/beziersplinecontinuity.html),
[G2 continuity derivation](https://turbo-sim.github.io/nurbspy/theory/g2_continuity.html),
[Bézier/Bernstein construction](https://pomax.github.io/bezierinfo/).
Equations and acceptance policy above are derived for this plan rather than
copied implementation code.

## Bounded direct native actions (0.5.0)

Diagnose unrounded native joins before candidate construction. Healthy ordinary
joins are no-ops; Default node still resolves existing curve/curve stars. Native
star materialization uses effective join and adjacent control coordinates from
a detached font. Both unrounded construction and normal drawing are bounded
against the original contour with `check_pair` or native-chain `chain_deviation`.
Corresponding masters must all pass. Adjacent candidates are validated together;
if a batch refuses, each cumulative candidate is checked against the original
contour, preserving accepted G2 joins and non-regression at affected neighbors.

Tunni plus harmonization is an optional internal candidate. The native candidate
must pass first. A refused balancing candidate restores and revalidates that
bounded native candidate. The raw control-point difference is formed before
normalization to reduce translation cancellation. The bound includes the
existing conservative numerical margin: the certified upper bound can slightly
exceed an exact theoretical displacement. Acceptance requires the certified
bound to fit, never a tolerance expansion to conceal uncertainty.
