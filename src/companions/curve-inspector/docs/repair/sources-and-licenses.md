# Sources, comparisons and licensing

Research date: **2026-10-09**. Revisions below are inspected snapshots, not promises
about current upstream releases or Glyphs 4 compatibility. Attribution, visible
source, a license and a qualified behavioral test are separate kinds of evidence.
An established author does not remove the need to validate a candidate.

## What is worth reusing

Existing tools cover important parts of this task. Native stars provide a
documented native G2 mechanism; SuperTool provides licensed harmonization and
Tunni computations; mekkablue and other authors provide useful comparison tools.
The new work is scoped proposals, shape bounds, exact state guards, effective
outline qualification, general-master verification and a shared human/agent
workflow. No inspected tool establishes all those requirements together.

**Proposed choice:** reuse native stars and the pinned SuperTool computation,
rather than develop another unconstrained optimizer. Treat existing tools as
candidate/reference implementations, not as substitutes for acceptance checks.

## Inspected upstream implementations

### SuperTool — Simon Cozens

Pinned revision: `ccc71ee39ef72c0c34267410d2b9ebee454ec98c`.

- [Repository snapshot](https://github.com/simoncozens/SuperTool/tree/ccc71ee39ef72c0c34267410d2b9ebee454ec98c)
- [Harmonization source](https://github.com/simoncozens/SuperTool/blob/ccc71ee39ef72c0c34267410d2b9ebee454ec98c/SuperTool/SuperTool%2BHarmonize.m)
- [Tunni source](https://github.com/simoncozens/SuperTool/blob/ccc71ee39ef72c0c34267410d2b9ebee454ec98c/SuperTool/SuperTool%2BTunniEditing.m)
- [License](https://github.com/simoncozens/SuperTool/blob/ccc71ee39ef72c0c34267410d2b9ebee454ec98c/LICENSE)

**Inspected:** Objective-C harmonization and balancing computations, command
sequencing, license and submodule dependency. The harmonization uses tangent-line
intersection ratios and translates the two handles to retain the join. Its full
command balances before and after. Tunni balancing equalizes endpoint-tangent
percentages within a segment. The code does not supply this plan's bounded-shape,
exact-state or general-master verification contract.

**License:** root Apache-2.0; the inspected computation files carry Copyright
2019 Google LLC notices. This is relevant Google-authored source provenance,
not evidence that Google Fonts endorses a universal repair algorithm.

**Dependency boundary:** native Cocoa/GlyphsCore and `SCGlyphsLib` support the
plugin. The pinned submodule revision is
`18e41c746e1c43db58af6b8ed2028156d983175b`. Inspected utility headers carry
Simon Cozens copyright/all-rights-reserved language, and an independent root
license was not established in this investigation. Do not assume SuperTool's
root license licenses a separate repository. **Do not import that submodule's
code.** Implement ordinary vector/intersection helpers independently.

The adaptation must preserve upstream notices, include Apache-2.0, identify
modified files, and retain any applicable NOTICE content. Record the source
revision and selected files. The engine now contains the attributed Python
adaptation with the full Apache license and modification notice; no full
upstream plugin or SCGlyphsLib code is copied.

### GreenHarmony — Alex Slobzheninov

Snapshot: `f657d4b88383cf7aae605ab4851d64e324eca648`.
[Source repository](https://github.com/slobzheninov/GreenHarmony/tree/f657d4b88383cf7aae605ab4851d64e324eca648).
Root license inspected: Apache-2.0.

**Inspected behavior:** tangent-intersection construction moves the on-curve
join. Its alternate layer handling follows compatible layer structure, not this
plan's complete native designspace verification. Good mathematical comparison;
it does not satisfy a fixed-join handle method or shape bound by itself.
Source and license were inspected; local Glyphs 4 execution was not performed.

### GreyHarmony — mekkablue / Rainer Erich Scheichelbauer

Snapshot: `b53e08659417321ef924cdb2415dd5197c693bbd`.
[Source repository](https://github.com/mekkablue/GreyHarmony/tree/b53e08659417321ef924cdb2415dd5197c693bbd).
Root license inspected: Apache-2.0.

**Inspected behavior:** related ratio computation translates the two handles
and fixes the join. It is an independent comparison for the selected handle
route. Runtime dependencies include the Glyphs Python/native environment;
documentation describes Glyphs 3 rather than providing Glyphs 4 qualification.
Source behavior takes precedence over ambiguous wording about moving nodes.
No built-in guarantee of this plan's maximum deviation was established.

### FixZeroHandles — mekkablue

Snapshot: `5adc4df2af84f05fe573fe29ab4fc68fd5f3e31d`.
[Source repository](https://github.com/mekkablue/FixZeroHandles/tree/5adc4df2af84f05fe573fe29ab4fc68fd5f3e31d).
Root license inspected: Apache-2.0.

**Inspected behavior:** reconstructs retracted handles through heuristic
fractions, handles quasi-straight cases, and can remove handles across compatible
layers. Useful for a later zero-handle milestone, but topology changes and
heuristic extraction are outside this v1. It is not silently invoked as a
preconditioner for a failed star or harmonization trial.

### mekkablue Glyphs scripts

Snapshot: `740112b054b047f5763381fb536fd3ab5ff893fb`.
[Repository](https://github.com/mekkablue/Glyphs-Scripts/tree/740112b054b047f5763381fb536fd3ab5ff893fb).
Root license inspected: Apache-2.0. Scripts depend on GlyphsApp and, depending
on the script, Foundation/Vanilla/repository helpers.

| Inspected script | What it does | Limit for this task |
| --- | --- | --- |
| `Paths/Green Blue Manager.py` | Manages smooth/corner states and handle alignment; some paths move the join | Not G2 shape-bounded repair; report mode can perform trial writes/restoration |
| `Interpolation/Dekink Masters.py` | Transfers selected handle-triplet proportions from a reference to compatible layers | Interpolation-oriented proportional repair, not general G2 verification |
| `Interpolation/New Tab with Uneven Handle Distributions.py` | Detects uneven tangent-intersection handle distributions | Detection/display, not a complete repair proposal engine |
| `Paths/Positional Harmonize.py` | Computes a positional G2 adjustment for an Arabic cross-glyph workflow | Narrow reference-glyph use rather than arbitrary joins |

`Interpolation/KinkFinder.py` was located, but its implementation was not fully
inspected in this investigation. Historical Tunnify and curve-to-line scripts
are described in official tutorials; this record does not claim their current
source availability or Glyphs 4 qualification was established.

The user's “Mike Blue” reference is understood as **mekkablue**. These repositories
and scripts provide attributable sources to compare and, subject to their actual
licenses, reuse. They do not make arbitrary live trial writes safe for preview.

### RMX Tools — proprietary behavioral reference

[Official manual](https://remix-tools.com/glyphsapp/manual).
The inspected manual's embedded date is October 2018; a recent crawl date does
not make that a newly released manual.

**Documented behavior:** Dekink handles tangent continuity, Harmonize targets
curvature continuity and includes dekinking, and Supersmooth addresses a further
curvature-change behavior. The suite also handles cases such as extracted
handles and intentional abrupt features. These product behaviors are useful
comparison goals. Native Glyphs star nodes must not be equated with RMX
Supersmooth simply because both names suggest smoothness.

No reusable RMX implementation or license was established. Treat it as
proprietary. Do not reverse engineer or copy its algorithm into this project.

The inspected MIT-licensed
[nmassi/glyphs-mcp snapshot](https://github.com/nmassi/glyphs-mcp/tree/2aea3aa4d6b74a8b59af159245525a3a6cd7cd76)
contains handlers that locate `RMXHarmonizer` and call methods such as
`dekinkOnly_`, `harmonize_` and supersmooth variants. Those handlers delegate to
the installed proprietary runtime; MIT wrapper licensing does not supply RMX
code or grant rights to it. A dependency on a licensed installed RMX runtime
would be a separate optional feature, not the selected shared engine.

## Google Fonts / fontTools and standard mathematics

The inspected SuperTool files have Google LLC copyright attribution. That is
the most direct relevant reusable computation found in this research.

[fontTools cu2qu](https://fonttools.readthedocs.io/en/latest/cu2qu/index.html)
provides cubic-to-quadratic approximation with an error tolerance.
[Cu2QuMultiPen](https://fonttools.readthedocs.io/en/latest/pens/cu2quPen.html)
supports interpolation-compatible conversion.
[bezierTools](https://fonttools.readthedocs.io/en/latest/misc/bezierTools.html)
provides standard curve utilities. These are useful engineering references,
but conversion and curve measurement are different from G1/G2 repair while
preserving the intended cubic design. No fontTools code is imported or pinned
as an engine dependency here; adding it later requires its exact license and
version in the build record.

Font Bakery's [official documentation](https://fontbakery.readthedocs.io/en/stable/)
is a quality-checking reference. This investigation did not establish a ready
Font Bakery or Google Fonts operation covering the complete requested repair
and native-star verification workflow. This is a bounded research finding,
not a claim that no other script exists anywhere.

Primary mathematical references:

- [Bézier spline continuity, Tino Weinkauf](https://people.kth.se/~weinkauf/notes/beziersplinecontinuity.html).
- [G2 continuity, nurbspy authors](https://turbo-sim.github.io/nurbspy/theory/g2_continuity.html).
- [Bézier/Bernstein and subdivision, Pomax](https://pomax.github.io/bezierinfo/).
- [Simon Cozens' harmonization derivation](https://gist.github.com/simoncozens/3c5d304ae2c14894393c6284df91be5b).

An independent code license for the gist was not established; cite its
mathematics rather than vendor it as licensed source. The engine's derivatives,
integral matrix and Bernstein bounds should be independently implemented and
verified. Mathematical formulas do not require adopting a proprietary plugin.

## Official Glyphs references

- [Super-smooth nodes](https://handbook.glyphsapp.com/editing-paths/#super-smooth-nodes): native intended behavior and stored/effective distinction.
- [GSPath native API](https://docu.glyphsapp.com/Core/GlyphsCore/GSPath/): primitive representation and conversion API.
- [Harmonization tutorial](https://glyphsapp.com/learn/harmonization): terminology and established tool comparisons.
- [Python API](https://docu.glyphsapp.com/): wrapper/native model reference.

These support intended behavior and API research, not a qualification record
for effective-outline extraction on this user's host. Do not reproduce the
handbook or proprietary manuals as bundled documentation.

## Local integration evidence

Integration checkout research reference: `09b2ac7e51dbe90fe270e9ffb86854f2585205dc`.
The checkout had unrelated uncommitted work during inspection. Paths below
identify the observed source; this document does not claim the working tree
is a reproducible release solely from that commit.

| Area | Observed repository paths |
| --- | --- |
| Reporter and current bounds | `src/companions/curve-inspector/glyphs_curve_inspector/plugin.py`, `README.md` in that companion |
| Current curvature helper | `src/companions/curve-inspector/curve_core/geometry.py` |
| Plugin identity | `src/companions/curve-inspector/bundle/Glyphs Curve Inspector.glyphsReporter/Contents/Info.plist` |
| Companion registration | `src/companions/sdk/glyphs_mcp_companions.py`, `src/bridge/glyphs_mcp_bridge/companions.py` |
| Manifest validation | `src/protocol/glyphs_mcp_protocol/models.py` |
| Reads and geometry hashes | `src/bridge/glyphs_mcp_bridge/outline_reads.py`, `src/protocol/glyphs_mcp_protocol/outline.py` |
| Coordinate application/restoration | `src/bridge/glyphs_mcp_bridge/outline_edit.py` |
| Script contracts | `src/protocol/glyphs_mcp_protocol/scripts.py`, script workflow/runtime code in the bridge |
| Packaging | `scripts/build_simple_v2.py` |
| Existing checks | `src/glyphs-mcp/tests/test_simple_v2_companions.py`, `test_simple_v2_curve_lifecycle.py`, build checks and `src/companions/TESTING.md` |
| Native wrapper and Reporter SDK | `skills/glyphs-mcp-development/assets/knowledge/docs/sdk/ObjectWrapper/GlyphsApp/` |

The inspected SDK reference revision is
`c0352321d30a06006f18e94d600f5caf43d06f1b`. It exposes the exact super-smooth
constant and native connection setter; its smooth Boolean setter uses ordinary
smooth state. These facts motivate independent exact guards.

The current display curvature helper substitutes zero for near-zero/nonfinite
speed or nonfinite curvature. Preserve display compatibility as needed, but do
not reuse that fallback as a repair acceptance diagnosis.

## Existing dekink-native workflow

[Reference snapshot](https://github.com/thierryc/dekink-glyphs4/tree/f6c33d969732716698e8a10e0714e1ec4b74a118/rebuild/dekink-native),
local observed skill: `/Users/thierryc/.codex/skills/dekink-native/`.
License inspected: Apache-2.0.

**Inspected:** geometry/native separation, HOI attribute access, candidate
minimality, interpolation sampling and qualification records. Its domain is
one axis, two ordinary masters and compatible closed line/cubic paths;
components, open paths and additional/special layers are excluded. Defaults and
native semantics do not transfer automatically to bounded G2 repair.

Historical apply fixtures record Glyphs 4.1.1 build 4108. The observed
2026-10-08 qualification notes also identify newer repair/source-residual paths
and broader interactions as pending native qualification. Do not represent
every current mode as qualified because an earlier fixture passed.

Reuse the workflow within its qualified scope for HOI-specific requests, and
reuse architectural patterns after license checks. General-master or combined
star/HOI behavior needs new disposable-font evidence. No installed/global skill
is changed by this documentation milestone.

## Future license and provenance checklist

Before bundling an adaptation:

1. Pin the exact upstream commit and files; keep a source digest and alteration
   record.
2. Preserve Copyright 2019 Google LLC and other applicable source notices;
   include the complete Apache-2.0 license and any applicable NOTICE material.
3. Identify modified/adapted files and maintain attribution in both native and
   skill bundles.
4. Exclude unverified `SCGlyphsLib` code and proprietary RMX implementation.
5. Inventory every actual runtime dependency and its license; native Glyphs is
   a required host, not redistributed engine source.
6. Verify that Curve Inspector and the skill bundle use the same canonical
   engine revision/digest and carry matching license records.

These research documents contain original planning text and links, not vendored
upstream algorithm source. Future licensing decisions and notices must describe
the code actually shipped, rather than claim that a proposed dependency is
already included.
