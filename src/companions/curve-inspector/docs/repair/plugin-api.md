# Integration and proposed plugin API

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



All `algorithm-extension.v1` fields in this document are **proposed**. They are
not supported tools or an implemented V2 protocol. Current behavior is identified
separately to prevent a metadata capability from being mistaken for a callable
operation.

The local `curve_repair.native.NativeAdapter` now supplies Python `analyze`,
`propose`, `verify` and guarded `apply` methods for the controller and thin helper.
This does not implement `algorithm-extension.v1` or create MCP tools. Human
application uses native glyph Undo and checked owned-edit compensation; scripts
retain V2's whole-font saved-baseline recovery contract.

## Current Curve Inspector and companion registration

**Researched local state:** Curve Inspector is a Reporter with bundle identifier
`com.ap.cx.glyphs-curve-inspector`. Its current companion manifest is:

```json
{
  "protocol": 1,
  "id": "curve-inspector",
  "version": "0.1.0",
  "capabilities": ["curve.measure", "curve.overlay"]
}
```

Retain that registration format and identity. Version the plugin when an actual
release changes it. The current validator accepts exactly the manifest fields;
do not add operation schemas there. Adding a future capability such as
`curve.repair.propose` advertises metadata only. It does not create discovery,
dispatch or an MCP tool.

The current companion SDK provides registration and lifecycle/view helpers.
It does not provide algorithm execution. The Reporter SDK has general and
conditional context-menu hooks, suitable for opening a controller for selected
joins. Repair code must never run inside draw or refresh callbacks.

## Initial route: existing V2 operations

**Proposed implementation using existing facilities:**

1. Inspect advertised environment capabilities and supported reads.
2. Bind exact document, glyph, owning layer and foreground/background targets.
3. Obtain source geometry and resolve requested coverage independently of the
   Reporter's capped display.
4. Run pure analysis locally when reads suffice. Use an existing
   `python_script` job for unsupported native state, detached native trials or
   native verification, following its saved-baseline rules.
5. Create an immutable proposal with exact state, measurements and coverage.
6. Apply supported coordinate edits through the guarded edit workflow, or use
   a narrowly scoped native script for star connections with independent exact
   guards. Recheck the complete proposal before the first write.
7. Verify through the same engine and qualified native adapter.

No new arbitrary Python endpoint is proposed. Script availability depends on
the advertised `script.native.v1` capability. The existing V2 script workflow
provides `font`, `targets`, `params` and `Glyphs`; its per-target context includes
the resolved target, index and total. Do not bind application to whatever happens
to be selected when execution starts.

Existing script limits include 128 KiB source, 64 KiB parameters and truncated
text output. Return a compact versioned summary and bounded diagnostics. Store
large detached analysis records in a planned, supported artifact mechanism when
available; do not assume an unimplemented result channel. A complete internal
record and a compact UI summary are different things. Truncation must not hide
verification failures or turn incomplete coverage into success.

## Exact source guards

**Researched limitation:** current outline reads and hashes represent a node's
`smooth` boolean rather than its exact connection and omit relevant HOI state.
Some native snapshots retain exact connection, but this does not make the whole
typed pipeline star-aware. A Boolean setter can demote a star.

**Proposed native fingerprint:** include, at minimum:

- V2 document identity, revision and resolved target identity.
- Glyph identity; owning foreground layer ID; foreground/background surface;
  actual layer identity; associated master and special-layer family.
- Path identity/order, closed state, direction, locks and topology.
- Exact coordinates and native node types/connections.
- Relevant node attributes, including HOI, and geometry-affecting layer state.
- UPM, axes, master locations, special-layer configuration and interpolation
  information relevant to the verification region.
- Components or other geometry dependencies if included in scope.

Use a versioned canonical serialization with exact finite coordinate encodings
and deterministic attribute ordering. Unknown geometry-affecting attributes or
unsupported native values block a trustworthy fingerprint; do not hash a
potentially unstable object `repr`. Persist the structured state alongside its
digest so a stale result can explain which guard changed.

Re-resolve the same owning layer and surface immediately before application,
then validate **all** guards before the first mutation. Connection-only, HOI-only,
lock, layer-family and designspace changes invalidate the proposal even if the
current coordinate hash is unchanged. There is no silent rebase onto new state.

## Detached trial and thread boundary

The native adapter captures source state and makes complete detached font copies
on the required Glyphs thread. It preserves axes, masters, special layers,
attributes and components. Native interpolation and effective-path extraction
also run where the native API requires them. Only immutable numeric geometry
and diagnostics are sent to background workers.

Trial setters affect detached objects only. Do not temporarily mutate the live
font and then restore it as a preview technique. Do not change font grid settings
to obtain precision. Any temporary per-layer rounding override must be separately
qualified and restored on all exits.

Cancellation invalidates a generation and discards detached state. An old worker
must not publish a preview into a switched document. Every cached effective
outline records its source fingerprint, engine revision and extraction version.

## Application and recovery

Preview-only authorization permits analysis and detached trials, not live edits.
An existing request to repair exact targets can authorize application without an
extra permission prompt. The controller's Apply action provides human
authorization for the shown proposal. Scope expansion or tolerance relaxation
requires a new explicit decision; elapsed time is not authorization.

V2 owns job lifecycle and saved-baseline recovery. Existing typed coordinate
edits retain their supported guards and recovery semantics. Native script
recovery is different: it reloads the entire saved font, discards later unsaved
changes, clears/replaces native state and yields a fresh document identity.
It is not selective patch rollback and cannot undo external effects.

The script wrapper disables native Undo during execution. Keep its restoration
offer active through verification rather than defaulting to a timed Keep before
results are known. Keep does not itself save or prove successful verification.
After Keep/Save ends the offer, do not imply it remains available. A timeout or
lost result must be reconciled through the existing job, not replayed blindly.

A future adapter may add narrow exception compensation for only the writes it
owns, provided exact post-write state still matches and restoration is checked.
This is an additional qualified mechanism, not a promise that every partial
script failure rolls back. Report partial application and any recovery failure
explicitly. Never interfere with another live job owning the same targets.

## Proposed `algorithm-extension.v1`

**Purpose:** a generic way for a plugin to provide computations while V2 owns
identity, validation, workflow and application. Implement only after demonstrating
benefit over the initial scripting route. Providers are trusted installed native
code, not sandboxed by a schema.

Register the extension separately from companion protocol 1. The proposed
descriptor has these fields:

| Field | Type / constraint |
| --- | --- |
| `protocol` | constant `algorithm-extension.v1` |
| `plugin` | `{id, bundleIdentifier, version}`; existing Curve Inspector identity |
| `engine` | `{apiVersion, revision, sourceDigest, qualificationId}` |
| `operations` | descriptors for `analyze`, `propose`, `verify` |
| `operations[].id` | stable operation name |
| `operations[].version` | independently versioned operation contract |
| `operations[].parameterSchema` | JSON Schema, draft 2020-12 |
| `operations[].resultSchema` | JSON Schema, draft 2020-12 |
| `operations[].requirements` | native features and qualified scope needed |
| `operations[].effects` | constant `detached-computation` for these operations |

Example identity fragment (illustrative placeholders, not release claims):

```json
{
  "protocol": "algorithm-extension.v1",
  "plugin": {
    "id": "curve-inspector",
    "bundleIdentifier": "com.ap.cx.glyphs-curve-inspector",
    "version": "future-release"
  },
  "engine": {
    "apiVersion": "1",
    "revision": "pinned-engine-commit",
    "sourceDigest": "sha256:build-generated-digest",
    "qualificationId": "host-specific-record"
  }
}
```

A provider computes diagnostics or proposals. It cannot bypass V2 by applying
an edit during `analyze`, `propose` or `verify`. V2 validates and applies only
edits supported by its own current contracts. No provider `apply` operation is
included. A generic discovery/dispatch mechanism is a future infrastructure
change, not three new dedicated MCP tools per plugin.

## Proposed parameter contracts

All operations require a versioned request, exact source reference and declared
scope. No default-to-whole-font or default-to-current-selection behavior is
permitted after targets have been bound.

| Operation | Required parameters | Result |
| --- | --- | --- |
| `analyze` | `source`, `scope`, `diagnosticPolicy`, `verificationRegion` | diagnostics, source fingerprints and coverage |
| `propose` | analyze parameters plus `method`, `maxDeviationEm`, `tunniBalance` | immutable proposal or explicit refusal/no-op |
| `verify` | `source`, `proposalId`, `expectedState`, `verificationRegion` | actual post-application measurements and coverage |

`method` is `native-star` or `supertool-handles`; no silent method fallback.
`maxDeviationEm` defaults to 0.001 and must be finite and positive.
`tunniBalance` defaults to false and belongs to the explicit handle route in v1.
Unknown fields, methods, unsupported schemas and mismatched engine versions are
rejected. Pure providers cannot claim native verification.

Illustrative parameter schema fragment for the method-specific part of `propose`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "type": "object",
  "additionalProperties": false,
  "required": ["method", "maxDeviationEm", "tunniBalance"],
  "properties": {
    "method": {"enum": ["native-star", "supertool-handles"]},
    "maxDeviationEm": {"type": "number", "exclusiveMinimum": 0},
    "tunniBalance": {"type": "boolean"}
  },
  "allOf": [{
    "if": {"properties": {"method": {"const": "native-star"}}},
    "then": {"properties": {"tunniBalance": {"const": false}}}
  }]
}
```

This fragment is not a complete request schema. The implementation milestone
must publish complete schemas for source, target, family, region, diagnostics,
edits and coverage, and test their round trips and validation failures.

## Proposed proposal/result contracts

Every result includes `schemaVersion`, `operationVersion`, engine provenance,
status, bounded summary diagnostics and coverage. Status is one of:

```text
ok | noop | refused | coverage_incomplete | stale | unsupported | failed
```

A proposal additionally contains:

| Field | Required content |
| --- | --- |
| `proposalId` | immutable identity tied to source state and engine policy |
| `targets` | exact document/glyph/layer/surface/path/node joins and dependency blocks |
| `sourceFingerprints` | structured exact native guards plus versioned digests |
| `edits` | explicit old/expected and proposed connection or coordinate state |
| `diagnostics` | G1/G2, signed curvature, degeneracies, corners/locks and reasons |
| `measurements` | before/after effective outlines, join movement, integral score, deviation bounds and units |
| `verification` | families, region, requested/evaluated locations, failures and exclusions |
| `policy` | method, tolerance, balancing, numeric policy and resource limits |

Connection edit records distinguish the exact native connection from smoothness.
Coordinate records contain exact old and new values. These are **proposal data**;
they do not imply V2 currently supports applying typed star edits.

Coverage names source segments and native locations separately. A result cannot
be `ok` when an explicitly required target or family was omitted. Failure reasons
include `undefined_curvature`, `incompatible_correspondence`,
`unresolved_deviation`, `excess_deviation`, `neighbor_regression`,
`locked_target`, `deliberate_corner`, `native_unqualified` and
`location_budget_exceeded`. Diagnostic text accompanies codes.

## Gates before a shared API implementation

Demonstrate at least one concrete advantage over scripting, such as eliminating
script duplication while preserving exact native guards and producing reliable
typed proposals. Define provider lifecycle, restart/version behavior, cancellation,
main-thread scheduling, size limits, errors and stale-state handling.

Typed star application requires exact connection support across reads, hashes,
validation, mutation, restoration and tests. HOI must have its own supported
attribute contract if it is included. Retain script routing until these gates
are met; advertising a future capability is not a workaround.

## Line/curve results in engine 0.3.0

The `native-star` method name remains stable and selects the native super-smooth
connection for stars or raindrops. Node pairs identify the join; adjoining segments
need no explicit selection. `joinKind` reports `curve-curve`, `line-curve` or
`curve-line`. `selectionCoverage` reports exact requested/eligible/blocked counts
on accepted proposals; mixed blocked requests return an error with counts and
source locations instead of an implicitly reduced proposal.

Expanded chains report `deviationMetric=continuous native-chain chord correspondence`
and `integratedDifferenceEm2=null`. Diagnostics distinguish requested G2 joins,
generated internal G1 joins, native unrounded construction and grid-rounded
drawing continuity. `supertool-handles` rejects requested line/curve joins with
`unsupported_method`. Companion registration and MCP tool discovery are unchanged.

## Shared human direct-action API (0.5.0)

`apply_steps(scope, app, method="star", all_masters=False,
max_change_units=None, *, tunni_balance=True)` performs detached calculation
then guarded, verified, per-glyph application. `method` is `star` or
`default-node`; `None` uses `0.001 × font.upm` units. `prepare_path` exposes the
same detached computation and `commit_paths` the guarded native Undo commit.
These are bundled Python helpers, not new advertised MCP operations. They do
not add a native script rollback mechanism or bypass V2 saved-baseline rules.
`NativeAdapter` and existing agent proposal parameter schemas are unchanged.
