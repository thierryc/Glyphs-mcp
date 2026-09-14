# Beta 1 gaps 7–14 — sequential implementation plan

**Planning only. Implement one numbered step, test it, report the result, then
pause for user feedback before starting the next.** These are feature-audit gap
numbers, separate from the earlier P-series benchmarks. No implementation,
installation or new native qualification is claimed by this document.

Continue from [H6](../beta1-h6-kerning-discovery-20260914/report.md), committed as
`28b965dc`, using the current private lean source in `build/milestone7/desktop`.
Keep v1, unrelated work and previous measurements unchanged. The
[feature audit](../v1-v2-feature-audit-20260914/report.md) and
[high-priority plan](../beta1-gap-fixes-plan-20260914/plan.md) remain historical
records. The current source was inspected for this plan; running identities were
last qualified in H6 and must be verified again before implementation trials.

## Sequence and value

| Step | Deliverable | Example and benefit |
|---|---|---|
| 7 | Requested master metrics, axis positions and italic angle | “Read the Light master's fractional ascender and weight position.” Reliable values without a script or guessed axis order. |
| 8 | Requested production name, script and layer count | “Inspect these three glyphs before export.” Completes common metadata reads without fetching their outlines. |
| 9 | Bounded structure and optional nodes for one exact layer | “Explain this contour and component order.” Supplies inspectable geometry without a font-wide model. |
| 10 | Native master-compatibility evidence | “Which layers disagree, and what differs?” Separates Glyphs' verdict from an agent's explanation. |
| 11 | Bounded native instance metadata | “Which instances export, and at which axis positions?” Identifies export intentions without generating fonts. |
| 12 | Exact one-master width/sidebearing recipe | “Set A in Regular to width 600.25.” Avoids accidentally changing all layers. |
| 13 | Exact native kerning set/remove recipe | “Set this Regular A/V exception to −32.5, then remove it.” Supports deliberate edits independently of collision repair. |
| 14 | Stylistic-set listing and native proof-tab recipe | “List ss01–ss20 and show a proof of ss03.” Makes existing OpenType work easier to inspect and demonstrate. |

Steps 7–11 extend `read_entities`; steps 12–14 improve focused native workflows.
**No new MCP tool or job is proposed.** Preserve seven tools, five jobs, existing
selection fields, document IDs, native editing and Undo/discard behavior.

## Shared implementation and qualification gates

1. Freeze the source revision, installed sidecar/bridge identity, seven-tool
   catalog and configured skill hashes. Record unrelated work before editing.
2. Specify the requested fields, bounds, failure behavior and expected native
   values before implementation. Prototype uncertain native getters on disposable
   fonts first. Use native indexed collections and counts; do not serialize a
   complete collection merely to return its first few items.
3. Extend existing operation-specific read hooks, field validation and negotiated
   capabilities. Keep existing requests and responses unchanged when the new
   fields are absent. Missing private capabilities mean a coordinated update is
   required, not an earlier-private workflow or a hidden verification script.
4. Update focused references, invocation/routing tests and packaged mirrors through
   the existing mechanisms. Keep the entry skill compact. Reuse this connection's
   identity evidence and document ID; rediscover only after stale-document
   rejection or a changed target. Missing glyphs do not require document discovery.
5. Run focused tests, then the relevant lean regression, package/identity, skill
   ownership and routing gates. Respect existing module/architecture budgets;
   extract small read projections only where needed. Do not replace the adapter
   or add a generic document model to accommodate these fields.
6. For runtime changes, build a separately fingerprinted candidate and use the
   existing authorized installer. Preserve user work before any required shutdown.
   Verify loaded sidecar/bridge identities, capability negotiation and installed
   skill payloads. For skill-only steps, install the changed skills through the
   existing ownership/backup path; avoid redundant runtime installs or restarts.
7. Qualify isolated native behavior first, then public workflows in Glyphs 4 on
   fresh disposable copies. Reuse the three-master fixtures and pinned open-source
   Roboto Slab, adding only cases needed for this step. Never use a user font as
   the test target or modify the immutable baseline.
8. Publish one report per step: passed/failed/blocked/unverified assertions with
   expected and observed values, call log, identities, preservation evidence,
   performance, token estimates and reasoned agent/skill assessment. Explain the
   next step with an example, then pause. Missing required native evidence or an
   unresolved correctness failure prevents a pass and advancement.

For each new read, cover exact IDs, foreground changes, dirty/unsaved documents,
fresh values, stale document IDs, missing targets, unsupported fields and bounds.
Read-only work must preserve native objects, font data, history and dirty state,
with no save, metric synchronization, compilation or export as a side effect.
For native writes, define the intended changes and exact preservation requirements
before execution; compare Undo/Redo with native controls. Do not force a clean
dirty indicator or add custom Undo/recovery machinery beyond Glyphs' behavior.

Measure first attempt, one warm-up and five timed repetitions for small and
representative larger supported requests. Record sample counts, median, range,
p95 and maximum; measure initial discovery separately from known-ID reads and
include both in total workflow costs. Native callback execution, queue wait and
HTTP latency are separate measurements. Record load and probe overhead; retain
the native p95 below 50 ms/max below 200 ms targets and sample the two seconds
following relevant fixture/UI changes. A timing failure requires investigation,
not a cache or watcher by default. Do not erase H5's historical timing exception.

Use the H6/Report 06 token method: `tiktoken` 0.12, `o200k_base`, compact sorted
JSON with literal Unicode, `{name, arguments}` plus one parsed response body;
count skill/reference text separately. Label estimates, not billed usage. Compare
minimal requested fields with optional detail, including any extra calls. Retain
v1 comparisons as historical unless the same task is freshly rerun unchanged.

## 7 — master metrics, axis values and italic angle

**Scope.** Add explicitly requested `ascender`, `capHeight`, `xHeight`,
`descender`, `italicAngle` and `axes` to the existing exact-master and master-page
reads. Proposed capability: `master.properties.v1`. Existing `id`/`name` requests
remain compact and unchanged. This reads master defaults, not per-layer metric
inheritance, export line metrics or an inferred designspace.

Proposed request:

```json
{
  "document_id": "<retained document ID>",
  "entities": [{"kind": "master", "id": "<exact native master ID>"}],
  "fields": ["id", "ascender", "descender", "italicAngle", "axes"]
}
```

The optional `axes` value contains native-order items with `axisId`, `tag`,
`name`, `index`, `internalValue` and `externalValue`, plus total/returned/complete
information. Reuse this projection in step 11. Obtain positions from current
native internal/external axis APIs, not the deprecated `axes` alias or assumptions
that positions 0/1 always mean weight/width. Label unavailable values explicitly;
do not calculate missing mappings. Axis descriptors occur once per returned axis,
not once per coordinate representation.

Start with at most 32 axes per owner and 256 returned axis items across a request;
scalar requests retain the existing 100-master bound. Preflight native counts and
reject an over-budget request with a narrower-scope instruction before projecting
values. These are proposed safety limits, not Glyphs application limits; lower
them if native timing requires it. Do not silently clip axis positions.

**Precision finding.** The installed Glyphs 4 Python wrapper casts `ascender`,
`capHeight`, `xHeight` and `descender` getters to `int`. Its native default getters
must be qualified directly against fractional values before choosing the bridge
access path. Preserve the value actually stored by the host, rather than claiming
fractional support from a Python property name. `italicAngle` must remain distinct
from applying a mechanical slant job.

**Changes.** Existing master field validation/projection and protocol capability;
`skills/glyphs/references/master-reads.md`, related layer/slant cross-references,
packaged mirrors and focused master/protocol/routing tests. The adapter is already
at 500 lines; prefer a small dedicated projection helper over expanding it or
loosening limits automatically.

**Pass gate.** Three masters with duplicate names, fractional/negative metrics,
zero/nonzero angles, reordered axes, custom tags and native internal/external
mapping differences. Verify exact IDs and values in both exact and page reads,
no-axis and over-budget cases, dirty live changes, default compactness and exact
preservation. Confirm that reads neither set the angle nor slant outlines.

**On pass:** Next is step 8: three small glyph fields for routine inspection.

## 8 — missing glyph metadata

**Scope.** Add `productionName`, `script` and `layerCount` to explicitly named
glyph reads; proposed capability `glyph.metadata.v1`. Retain the 100-glyph limit
and `{ "kind": "glyph", "id": "A" }` selector. Names-only inventory remains
unchanged. No Unicode allocation, export generation or general glyph-information
database is included.

Read production name and script through their native getters. State that the
returned production name is source/native metadata, not proof of the name in an
exported binary. Use the native stored-layer count already qualified in H5,
without enumerating layers. Include stored special/backup layers consistently
with H5; do not invent separate background entries. Preserve distinctions among
empty, unavailable and numeric zero.

Example: `fields=["name","productionName","script","layerCount"]` gives the
requested metadata without fetching geometry or discovering the glyph again.

**Changes.** Glyph projection/field validation, protocol capability, focused
`metadata-reads.md`, mirrors and lean glyph/routing tests.

**Pass gate.** Default and explicitly assigned production names, scriptless and
non-Latin glyphs, export-disabled glyphs, ordinary/special/backup layers and a
missing glyph within a batch. Compare exact native values and count semantics;
retain whole-request rejection for a missing target. Prove the count path does
not traverse every layer and reads do not set metadata storage flags.

**On pass:** Next is step 9: bounded evidence for one selected explicit layer.

## 9 — path/component details and structural evidence

**Scope.** Extend the existing exact-layer selector with requested `structure`
and optional `nodes`; proposed capability `layer.structure.v1`. Require one
explicit glyph/layer per detailed request, independent of the active Edit View.
Retain existing compact layer measurements and active-selection reads.

`structure` reports native ordered shapes: mixed `shapeIndex`, kind, and for paths
the separate `pathIndex`, closed/open status, direction and node count. Components
report their native reference, full affine transform and native alignment state.
Include bounded anchor names/positions when structural evidence is requested.
Represent unknown native shape types explicitly rather than treating them as
paths. Do not decompose components or expand referenced glyphs.

`nodes` reports x/y, type, smooth, `shapeIndex`, `pathIndex` and `nodeIndex`, with
layer metadata returned once. Path indices count paths only; node indices count
all nodes, including off-curves. Reuse the established 64-default/256-maximum
node detail policy. Start with 64 shape and 64 anchor records; use native counts
to expose total/returned/complete for each collection and the overall evidence.
A partial contour must be visibly incomplete. Do not infer absence from omitted
records or present truncated evidence as an interpolation proof.

Reuse existing request-limit validation for the optional node bound where practical;
document the additive selector option explicitly. No new pagination machinery,
full-font model, topology edits or exposed object addresses. Node-type summaries
must not scan unlimited nodes just because coordinates were omitted: report only
bounded examined evidence, or native counts that do not require traversal.

**Changes.** A focused layer projection, field/capability validation, layer and
outline references, mirrors and mixed-shape tests. Keep `outlineHash` an opaque
guard. Do not serialize the job patch model as a public inspection contract.

**Pass gate.** Mixed path/component order, transformed/aligned components, cubic
and straight paths, off-curves, open/empty/degenerate layers, anchors and limits
exactly at and above every boundary. Compare with an independent native oracle,
including fractional geometry and bounds, and prove no object replacement or
font mutation. Unknown or unsupported native values remain explicit.

**On pass:** Next is step 10: use native compatibility checks with this evidence.

## 10 — native master-compatibility diagnostics

**Scope.** Add a requested `compatibility` projection for one explicit glyph;
proposed capability `glyph.compatibility.v1`. Return Glyphs' `mastersCompatible`
verdict and opaque per-layer `compareString()` separately from observations about
structure. Do not parse the undocumented string encoding or construct another
compatibility engine. The agent may explain observed differences with exact
layer/shape/path locations, but must not replace an unavailable native verdict.

Include examined layer IDs, master associations, native classification and
special-layer metadata. Reuse H5 and step 9's projections rather than embedding
every node from every layer. A subsequent step-9 request supplies detailed nodes
for one layer when needed. Identify backup/special relationships from native
evidence; only call a layer excluded when that exclusion is verified. Do not
invent brace/bracket grouping rules or claim a backup affects the native verdict
without observing that behavior.

Preflight the whole glyph before invoking potentially unbounded native checks.
Propose initial ceilings of 32 layers, 256 shapes and 1,024 nodes per glyph, with
bounded per-layer anchor evidence. Qualify and reduce these ceilings if needed;
the older candidate's larger bounds are not a performance qualification for this
build. Above the ceiling, return an explicit unavailable native verdict and
incomplete evidence with counts/reason. A subset result must never masquerade as
the native verdict for the whole glyph. There is no full-font compatibility scan
in this step.

The [separate compatibility record](../v1-v2-feature-audit-20260914/separate-compatibility-record.md)
contains useful fixture/projection work. Reuse it selectively after review, not
by copying that candidate over this source. **Do not integrate its normalization,
reorder patch, job, hint-recovery or Undo changes.** Existing `start_nodes` remains
a separately requested and qualified repair workflow.

**Changes.** Bounded native projection, capability validation, master-compatibility
skill opening, focused playbook/invocation prompt, mirrors and contract tests.
An inspection request must not launch an edit-preparation job.

**Pass gate.** Reuse the reproducible MasterCompatibilityTest fixture on disposable
copies: compatible control, shifted starts, reversals, reordered shapes, missing
nodes, line/curve mismatch, anchor/reference differences, open and ambiguous
contours, special and backup layers. Record the actual native verdict even when
it differs from an intuitive structural rule. Verify exact issue locations,
bounded/unavailable behavior, dirty inspection and preservation. Report technical
compatibility separately from visual interpolation quality and specific manual
Glyphs actions; automated repair qualification remains pending outside this step.

**On pass:** Next is step 11: inspect instances without generating them.

## 11 — minimal instance inspection

**Scope.** Add a bounded `instances` collection selector within `read_entities`;
proposed capability `instances.list.v1`. Requested fields: native `name`, `type`,
`exports`, `visible`, `isItalic`, `weightClass`, `widthClass` and optional step-7
`axes`. Keep classification values distinct from axis positions and visibility
distinct from export eligibility. Unknown instance types remain raw native values
with an explicit unknown classification.

Use the existing page/cursor pattern and native collection order. Start with a
maximum of 100 instances and the step-7 aggregate axis budget; ask for a smaller
page when requested axes exceed that budget. No `interpolatedFont`, instance
materialization, compilation, export, STAT construction or variable-font engine.

The inspected wrapper does not establish a native persistent instance ID.
Verify this before freezing the response contract. If none is supported, return
the current native index as an observation, clearly not a durable edit target.
Do not invent an ID registry or assume names are unique. Bind page cursors to the
document and existing collection/boundary guards; explain their live, non-atomic
semantics and restart enumeration after an observed edit.

**Changes.** Small indexed collection projection and protocol routing/capability,
a focused `instance-reads.md` linked only for this intent, mirrors and tests.

**Pass gate.** Empty and multi-page collections, duplicate names, static/variable
instances, export-disabled/hidden instances, custom axes and reordered instances.
Compare native values, honest coverage, axis-budget rejection and stale cursors;
prove inspection produces no output file or generated font and preserves data.

**On pass:** Next is step 12: precise native changes to one master only.

## 12 — exact one-master width and sidebearing changes

**Scope.** Improve the spacing skill and focused native reference. No bridge,
sidecar, job or tool extension. Explicitly distinguish the existing all-stored-layer
`width_delta` job from a request to set one master's absolute width or bearing.
Keep the current all-layer job unchanged.

Recipe: retain the document target, resolve exact ordinary master/layer IDs,
validate the entire explicit glyph set, read current values/keys/alignment,
describe the intended invariant, perform native setters in the existing native
Undo grouping, then verify exact read-back and unrelated masters. Reuse the
qualified precision recipe and restore transient flags in `finally` when needed.
No silent metric-key removal, alignment disabling or `syncMetrics()`.

Specify what the request means before writing: a width-only change, a bearing
change that preserves advance, or one that preserves the opposite bearing have
different effects. Do not promise all of width/LSB/RSB and absolute outline
positions can remain fixed while changing one of them. Preserve drawn shape under
an explicitly expected translation; verify anchor/component behavior too. Treat
empty layers separately because outline-derived bearings may be undefined.

**Pass gate.** Fractional absolute width, positive/negative bearings, unchanged
masters, metrics keys, aligned components, marks, empty outlines and populated
hints/metadata. Qualify native setter effects, exact values, preserved shape and
references, native Undo/Redo and repeat-as-no-op behavior. If native keys/alignment
prevent the exact request, report the blocker rather than forcing it. Scripts do
not gain MCP `discard_job` or rollback on exception; preflight before writing and
report partial native failures accurately without building a recovery framework.

**On pass:** Next is step 13: deliberately set or remove a stored kerning pair.

## 13 — arbitrary kerning set/remove through native workflow

**Scope.** Add a precise recipe to the kerning skill/reference using H6 discovery
and existing exact stored-pair reads for verification. Collision correction is
not an arbitrary setter. No new editing tool, job or kerning engine.

Resolve one exact master, direction, glyph names or verified native group keys;
state whether the target is a glyph exception or a group pair. Record exact stored
presence/value before editing, keeping absent distinct from zero. Preflight all
explicit operations, use native set/remove APIs, then verify the stored record
and unchanged out-of-scope records and group assignments. A group-pair edit may
intentionally change effective spacing of its members: do not promise unchanged
rendered group peers while changing that group value.

**Pass gate.** Glyph/glyph, group/group and mixed keys; absent, zero and fractional
values; set, replace, remove and no-op repeats; native supported directions and
missing targets. Verify exact storage and native Undo/Redo on disposable fonts.
Qualify write-direction support independently of H6's successful reads. Preserve
other stored pairs and exceptions. If an exact native operation or its restoration
cannot be verified, state that limitation and give a concrete UI route; do not
substitute a collision job or implement a custom undo manager.

**On pass:** Next is step 14: a convenient stylistic-set listing and proof tab.

## 14 — stylistic-set listings and native proof tabs

**Scope.** Extend the existing OpenType native reference and invocation/routing
examples. Reuse the installed offline KDB and qualified Glyphs 4 API notes; pinned
official source text remains unchanged. No feature-editing or tab MCP tool.

List actual `ss01`–`ss20` feature objects, requested labels/localizations,
automatic/disabled status and bounded source snippets. Report missing labels
without inventing friendly names or attempting to derive complete substitution
behavior from a simple text match. Listing alone must not compile or regenerate
features. Compile/export/shaping remain distinct evidence levels.

For an explicitly requested proof, use the intended font's native tab API with
explicit test glyphs, controls and the intended feature setting. Reuse the task's
tab for revision instead of repeatedly creating tabs; retain ownership of the
task-created tab so cleanup cannot close user tabs. Do not imply a tab or successful
compilation proves a feature works. Verify visible substitution and controls where
that is the requested outcome, recording the selected master and feature state.

**Pass gate.** Multiple/localized/missing labels, disabled and automatic sets,
long source, missing proof glyphs, Unicode-less alternates, multiple documents,
three masters, existing user tabs and repeat reuse/cleanup. Read-only listings
preserve font data; proof trials preserve unrelated tabs and restore incidental
view settings. Compilation changes require the existing explicit edit scope and
separate preservation evidence. No save or export is added merely to open a tab.

**On pass:** Publish the updated gap coverage and remaining intentional omissions.
Choose subsequent work from that evidence; do not advance to a new milestone
automatically.

## Recommendation and first delivery

Implement all eight selectively in this order. Steps 7 and 8 offer the quickest
routine benefit. Steps 9–11 require bounded native qualification, particularly
mixed-shape indices, whole-glyph compatibility cost and instance identity. Steps
12–14 close workflow gaps using existing native operations and focused guidance.

The first implementation delivery is **step 7 only**: requested master properties,
fractional and axis-mapping evidence, tested/installed candidate, compact skill
guidance and a short report. After its pass and user feedback, proceed to step 8.
No source change or new installation has been made as part of this plan.
