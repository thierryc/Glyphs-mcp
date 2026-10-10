# Implementation plan

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



## Current deliverable

**Current scope:** the user subsequently authorized continuing implementation.
Engine, native adapter, controller and skill source now exist in the companion.
Independent native evidence and installed UI qualification on the ordinary
two-master fixture are recorded. V2 protocol/server changes and working-font edits remain outside this work.

**Repository decision, revised 2026-10-09:** retain one Glyphs MCP repository.
Keep Curve Inspector at `src/companions/curve-inspector/` and its repair design
at `docs/repair/` inside that companion. Add the future shared `curve_repair`
module there, beside the existing `curve_core` and Reporter package. Place the
skill source under the companion's `skill/` folder and bundle it with the engine.
Managed `skills/` registration requires a release pointing to its actual immutable
source commit; do not advertise an uncommitted skill at an older commit.

This supersedes the earlier independent-engine-repository proposal. The plugin
already depends on build and regression infrastructure in this repository;
extracting it would create extra release and integration coordination without
a demonstrated benefit. Separate responsibilities in modules, not Git
repositories. The temporary planning repository is preserved outside the active
checkout for recovery. Existing source, identities and runtime behavior remain
preserved. Subsequently authorized implementation extends the companion in place.

## What already exists

**Researched facts from the earlier 0.1.0 snapshot:**

- Curve Inspector has a Reporter, a pure `curve_core` package, cached drawing,
  bounded main-thread curve copying, background computation, and coalesced
  refreshes. Its current display examines at most 128 raw cubic segments,
  with additional path/node/work caps and explicit coverage information.
- That display reads source cubic coordinates. It does not establish inspection
  of native star-adjusted effective outlines. Its current refresh source key
  includes geometry and coverage but not exact connection/HOI attributes.
- Companion protocol 1 registers plugin metadata and capability strings.
  It does not register operation providers or callable schemas.
- V2 has advertised reads, `python_script` jobs, and guarded coordinate edits.
  Exact star connections and HOI state are not fully represented in its current
  read schema or geometry hash.

The existing display limit cannot become the repair limit by accident. Repair
must independently resolve every target in the requested scope. Any resource
limit or missing target is reported as incomplete coverage.

## Component boundaries

| Component | Responsibility | Boundary |
| --- | --- | --- |
| Geometry engine | Derivatives, G1/G2 diagnostics, SuperTool candidates, shape measurements and refusal rules | Pure Python; no Glyphs objects or UI |
| Native adapter | Exact targets, detached copies, native star trials, primitive outlines and interpolation | Glyphs access on the required native thread |
| Proposal model | Source state, edits, measurements, coverage and provenance | Immutable; no apply side effects |
| Repair controller | Scope, method, tolerance, proposal lifecycle, preview, apply and verify | Writes only after existing authorization covers application |
| Reporter | Cached comb visualization, including approved preview data | No repair from drawing, enablement or refresh |
| Agent skill | Diagnosis, scope, tolerance, orchestration and explanation | Imports the same bundled engine |

**Proposed packaging:** this Glyphs MCP repository owns the canonical
`curve_repair` module inside the Curve Inspector companion. Release
artifacts include its revision, engine API version, source digest, license
notices, fixture version and native qualification identifier. Curve Inspector
and skill packages must agree on these values. A build fails on divergence.
There is no second algorithm implementation in the UI or skill and no import
from an absolute developer path.

The existing visual comb implementation should be reused where suitable.
Repair diagnostics must represent undefined curvature explicitly; the current
display helper's zero-curvature fallback for invalid speed is not an acceptance
rule. Either share a corrected, compatible primitive or adapt engine results
to the display, with one authoritative repair calculation.

## Repair policy

1. Resolve source targets and exact state, including deliberate corners and locks.
2. Diagnose stored and, where qualified, effective geometry.
3. Trial native star connections on detached fonts by default.
4. Trial SuperTool handle harmonization only when explicitly selected.
5. Apply optional Tunni balancing only when requested; validate the complete
   resulting candidate again.
6. Accept only with compatible correspondence, defined curvature, bounded
   deviation, no neighboring-join regressions, and sufficient declared coverage.
7. Present a proposal and before/after view. Apply within the authorized scope
   only after revalidating its source state.
8. Verify actual native results and retain the existing recovery lifecycle.

Maximum outline deviation defaults to **0.001 em**. Resolve that to font units
using the source UPM and record both values. Changing the tolerance invalidates
the proposal. Stored-coordinate preservation is a diagnostic, not a substitute
for this limit.

Corners are not automatically converted. Locked targets are not changed.
Already acceptable joins produce explicit no-ops. G1 and G2 are both in scope;
a smooth flag alone proves neither. Ambiguous or degenerate cases are refused
instead of silently relaxed.

HOI remains a distinct interpolation-trajectory operation. The existing
`dekink-native` workflow has a narrower qualified domain and is not evidence of
general-master repair. Native stars, RMX Supersmooth, and HOI are distinct
behaviors despite similar terminology.

## Human interface

**Proposed choice:** add an **Inspect & Repair…** command to Curve Inspector.
Use a small controller containing scope, method, maximum deviation, diagnostics,
coverage, before/after preview, Apply and verification status. Add context-menu
entry points for selected joins using the existing Reporter SDK hooks.

The command and controller operate while the overlay is disabled. Enabling the
Reporter never changes a font. Drawing reads immutable cached data; native
trials and application run outside drawing and refresh callbacks. Continue to
honor current worker generations, coalescing, graphics-state restoration and
active-view invalidation. Do not introduce global redraw storms.

Use the existing comb renderer for previews. Preview cancellation destroys
detached trial state without editing the original. Document switches, source
changes, layer/surface changes, connection/HOI changes and tolerance changes
invalidate the proposal. Application re-resolves the owning document and layer,
not the current selection alone.

Effective-outline inspection requires a new qualified source representation and
a cache key including all geometry-affecting state. A raw cubic comb must not
be labeled as the effective star outline.

## Initial V2 integration

Keep document identity, job lifecycle and saved-baseline requirements in V2.
Use its existing advertised reads, script jobs and supported guarded coordinate
edits. A native script additionally checks exact connections, relevant node and
layer attributes, coordinates, owning layer, foreground/background identity and
the relevant master-family state.

V2's current `smooth` boolean can collapse star state. Native star application
must use exact native connection operations and its own guards, not infer a
star from `smooth=True`. Do not advertise typed star mutation until exact state
is covered by reads, hashes, edit validation, mutation, restoration and tests.

Script recovery reloads the whole saved font and discards later unsaved changes.
It is not selective patch rollback. Keep the restoration offer active through
verification; do not automatically finalize a script job before verification.
Native analysis conducted through a script follows the same script lifecycle
and baseline constraints even when the algorithm intends only detached trials.
Detailed integration requirements are in [plugin-api.md](plugin-api.md).

## General-master verification

Multiple axes, extra masters and special-layer families remain required.
Preserve their full native model in detached trial fonts. Evaluate each
compatibility/substitution family separately and disclose unhandled families.

The declared verification region includes masters, intermediate/brace layers,
configured instances, alternate-layer boundaries, a five-position lattice per
axis and independent interleaved locations. Count unique locations before the
run. The cap is 4096 per proposal; excess requires an explicitly narrower
region and an updated coverage contract. Never truncate silently.

Effective-outline extraction and source-to-effective correspondence are gates.
Finite designspace checks establish sampled evidence only. See
[verification.md](verification.md) for the full contract.

## Milestones and acceptance

| Milestone | Deliverable and acceptance | Main unresolved risk |
| --- | --- | --- |
| 1. Investigation | The requested documents, mathematical derivations, source/license comparison and specified reference cases; explicitly record native unknowns | Native stars beyond documented intent |
| 2. Pure engine | Tested derivatives, undefined states, G1/G2 diagnostics, pinned SuperTool adaptation, continuous bounds, refusal cases and repeat no-ops | Degenerate and interacting geometry |
| 3. Skill and native adapter | Shared engine, detached trials, exact guards, authorized scripting application and general-master coverage records | Effective correspondence, special families and sampling cost |
| 4. Curve Inspector integration | Controller, preview, effective comb support and apply/verify workflow; existing Reporter lifecycle tests still pass | UI freshness and native extraction |
| 5. Shared API, if justified | Demonstrated benefit over scripts; generic extension and exact star support, or an explicit documented deferral | Compatibility and recovery semantics |
| 6. Qualification and packaging | Disposable-font trials, visual review, reproducible engine bundles, notices and host/build records | Host/build and export differences |

The writing portion of milestone 1 is complete. Milestone 2 is implemented with
analytic tests. Milestone 3 has adapter/skill code and independent native evidence;
conditional-family and other stated gates remain. Milestone 4 has controller and
Reporter integration with unit checks and installed native UI evidence on the
ordinary two-master fixture.
Milestone 5 is deferred: a generic extension has not demonstrated a necessary
advantage over supported scripts. Milestone 6 packaging is reproducible;
qualification remains scope-specific. Executed evidence is in `qualification/`
in the companion; reference cases in this plan are not all claimed as passes.

## Deferred work

- Zero-handle extraction and topology changes.
- Line-aware SuperTool handle candidates (native raindrops are implemented in 0.3.0).
- G3 smoothing and global contour optimization.
- Generalizing HOI repair beyond the existing qualified domain.
- Continuous guarantees over arbitrary nonlinear multidimensional interpolation.
- Export-format equivalence until independently qualified.
- Generic provider infrastructure before a concrete advantage over scripting.

## Decision record

**Proposed choices:** one existing Glyphs MCP repository; one Curve Inspector
companion and installation; a separate internal reusable engine module;
native stars first;
fixed-join SuperTool handles as an explicit method; Tunni off by default; shared
engine; 0.001 em default maximum deviation; no claims of global optimality;
general-master support remains a requirement rather than being silently reduced
to two masters.

**Unverified assumptions:** the host exposes trustworthy effective primitive
paths from detached fonts; source/effective correspondence can be established
without changing topology; detached native interpolation reproduces all relevant
special-layer behavior. Failure of any assumption yields a refusal or incomplete
coverage record, not permission to inspect raw paths as a substitute.
