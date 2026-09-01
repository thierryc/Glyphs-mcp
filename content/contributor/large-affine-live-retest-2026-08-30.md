# Large cross-master affine live retest

> Historical measurement: grid-snapped construction and grid-normalization
> recommendations in this report are superseded by v2's central floating-point
> scope. Current geometry is exact-only; global automatic alignment is
> preserved and native coordinate rounding blocks the preview.

## Result

On 2026-08-30, the implementation from commit `516a72c5` was installed as a
Glyphs 4 developer-link build and tested on the 422-glyph disposable
`Dactylotype` source in Glyphs 4.0.1 build 4004.

The release gate **failed before apply**. The new runtime and generic
`transform` contract loaded correctly, but the intended nine-master italic
preview did not complete successfully:

- the canonical layer-target form failed after `147.406s` because one selected
  empty layer contained no geometry;
- an equivalent shape-and-anchor-target form reached the `300s` transport
  timeout and continued occupying the server for more than another `300s`;
- no immutable preview ID was returned, so no `apply_change` was attempted;
- no save was attempted and the saved nine-Roman-master source stayed intact.

The under-two-minute objective is therefore not met. The live result also
shows that the automated 422-glyph surrogate does not exercise the dominant
native-host costs or empty-layer behavior.

## Safety and restoration

The open document before the retest was the known unsaved 18-master residual
from the original run. Before discarding it, the complete 422-glyph residual
was saved into a separate recovery package. The original saved disposable
package was not overwritten.

Glyphs was then restarted with the saved nine-Roman-master source. Its initial
and final observable state was:

| Property | Before | After |
|---|---:|---:|
| Masters | 9 | 9 |
| Instances | 29 | 29 |
| Glyphs | 422 | 422 |
| Unsaved changes | No | No |
| Apply calls | 0 | 0 |
| Save calls after restart | 0 | 0 |

The on-disk source modification time remained unchanged. The timed-out work
was preview-only and detached; after the server stopped responding, Glyphs was
restarted without saving and the clean nine-master source was reopened.

## Runtime evidence

The first live preflight exposed deployment skew: the running server reported
API 2.0 and version 2.0.0 but did not advertise `transform` or
`collection.index`. Testing paused until the committed build was installed and
Glyphs restarted.

The retest runtime reported:

| Field | Value |
|---|---|
| Server | Glyphs MCP 2.0.0 |
| Runtime ID | `2.0.0+5e4063a711de` |
| Code hash | `5e4063a711de3abeda09d7cb7ce9014c0574e5c78d058a8f7271e2506ff07286` |
| Glyphs | 4.0.1 build 4004 |
| Python | 3.14.6 |
| Canonical schema | 7 |
| Knowledge corpus | `2026.08.29` |
| Glyphs SDK revision | `0f5422db727b78cb42abfb386f33ae0b382b0c4d` |

The live registry included generic `transform`, `collection.index`, semantic
verification, and all four component-composition modes expected by the new
implementation.

Pinned evidence used for the test:

- `handbook.041-font-info-masters`;
- `handbook.068-interpolation-interpolation-masters`;
- `handbook.069-interpolation-interpolation-setup-instances`;
- `handbook.058-reusing-shapes-components`;
- `glyphs4.component-alignment-state`.

## Timing

The table separates server-reported duration from externally observed waiting.
When the client timed out or was terminated, no reliable server stage timings
were returned.

| # | Step | Result | Server/observed time |
|---:|---|---|---:|
| 1 | Load new runtime and inspect registry | Pass | `20ms` server |
| 2 | Resolve clean disposable document | Pass | `9ms` server |
| 3 | Search and retrieve pinned construction evidence | Pass | `<0.5s` observed |
| 4 | Cold canonical master read | Fail budget; client stopped waiting, server kept running | `>300s` effective |
| 5 | Identical cached canonical master read | Pass | `117ms` server |
| 6 | Preparatory four-master removal preview | No typed payload; not applied | about `293s` client plus about `90s` queued continuation |
| 7 | Reference preview: nine duplicates plus one layer transform | Typed error: `transform target contains no selected geometry` | `147.406s` server |
| 8 | Equivalent preview: nine duplicates plus shape/anchor transforms | Client timeout, no preview ID | `300s` client |
| 9 | Runtime-health request queued after timeout | Timed out while preview continued | another `300s` |
| 10 | Short process sample during continued work | Main thread continuously in Python tuple iteration; server thread waiting on a lock | `3s` sample |
| 11 | Restart and final document audit | Pass: clean 9/29/422 source | `26ms` server |

The reference preview exceeded the complete `<120s` release budget before
application or validation. The workaround remained active for more than
`600s` server-side and required a restart.

## Reproduction

1. Install the build containing commit `516a72c5`, restart Glyphs 4, and verify
   that `get_server_info` reports runtime ID `2.0.0+5e4063a711de` and generic
   `transform` support.
2. Open a clean disposable package with 422 glyphs, nine Roman masters, 29
   instances, and no unsaved changes.
3. Prime one canonical read, then submit one `preview_change` containing nine
   consecutive master `duplicate` operations. Each duplicate sets its final
   name, index, `italicAngle=12`, and matching `wght`/`wdth`/`ital=12`
   coordinates.
4. Add one layer-target `transform` over the 3,798 new master layers using
   matrix `[1, 0, 0.2125565616700221, 1, 0, 0]`, origin `[0, 0]`, grid
   quantization, paths/anchors/components, component conjugation, and
   `explicit_noncommuting` alignment.
5. Observe `invalid_request` after about 147 seconds because at least one
   selected layer is empty.
6. Repeat with exact shape targets plus exact anchor targets so empty layers
   are excluded. Observe a 300-second client timeout, continued server
   occupation, and no preview ID.

No private path, recovery filename, font data, or Python source is required to
reproduce the failures.

## Findings and suggestions

### P0 — empty members incorrectly invalidate a collection transform

`_transform_reference` rejects every selected layer whose individual touched
path list is empty. A whole-font layer transform therefore fails on ordinary
empty glyphs such as spaces even when the transaction transforms tens of
thousands of nodes elsewhere.

Suggested fix: allow empty members inside a multi-target transform and reject
only when the aggregate selected target set produces zero geometry changes.
Keep unsupported shape kinds and singular component conjugation blocking.

Acceptance test: include at least one empty master layer among 3,798 selected
layers; the preview must transform every non-empty layer, leave the empty layer
unchanged, and report its skipped/no-op count.

### P0 — client cancellation does not cancel preview work

After the 300-second MCP deadline, the preview kept the main Glyphs thread busy
for at least another five minutes. `get_runtime_status` queued behind it and
also timed out. The client received neither a preview ID nor a terminal
operation receipt.

Suggested fix: propagate request cancellation/deadlines into detached preview
planning and verification, check a cancellation token between bounded shards,
release the document/read lock, and persist a terminal cancelled receipt.
Runtime-health and stable-document-status reads should not wait behind a
detached preview.

Acceptance test: cancel during master duplication, transform, canonical diff,
and native equivalence. In every phase, the call must terminate within a small
bounded grace period, return an operation ID with `cancelled` classification,
leave the live fingerprint unchanged, and allow an immediate health/read call.

### P0 — the native live path still misses the performance target

The cold canonical read exceeded five minutes effective time. Its identical
cache hit took 117 milliseconds, proving that reuse is valuable, but preview
planning still took 147 seconds before an early geometry error and more than
600 seconds for the equivalent non-empty-target form.

A three-second process sample showed the main Glyphs thread continuously in a
Python tuple iterator while the MCP server thread waited on a Python lock. This
is consistent with synchronous canonical/native enumeration or comparison on
the main thread, not network latency.

Suggested fixes:

1. Build or refresh the fingerprint-keyed canonical baseline once when the
   document becomes stable, outside the timed workflow where possible.
2. Reuse that exact baseline, its entity indexes, and native identity map in
   preview, constraint evaluation, and validation.
3. Keep Glyphs main-thread work limited to the smallest native snapshot and
   final mutation boundaries; run canonical transforms, diffs, and semantic
   equivalence over immutable shards off the main thread.
4. Profile and remove repeated tuple/list materialization in layer/shape/node
   enumeration and requested-effect comparison.
5. Preserve the cache across failed or cancelled previews when the live
   fingerprint is unchanged.

Acceptance test: on the live disposable source, cold read, preview, apply, and
validation together must finish below 120 seconds. Report per-stage timings on
success, typed validation errors, cancellation, and timeout.

### P1 — error and timeout receipts omit the promised evidence

The 147-second typed error returned only total duration and
`invalid_request`; it omitted `stageTimings`, equivalence evidence, normalized
paths/deltas, rollback classification, and recovery evidence. The timeout
returned no operation ID at all.

Suggested fix: allocate an operation ID before expensive work, record stage
timings incrementally, and return the same bounded evidence envelope for every
terminal result. The stage in progress at cancellation or failure must be
named explicitly.

### P1 — static-instance-to-master materialization remains untyped

The saved live-gate baseline already contains the four Roman cross masters.
If the full five-to-nine Roman setup must also be rerun from the matching
static instances, the current generic `duplicate` operation cannot express
Glyphs’ authoritative “Instance as Master” interpolation. It duplicates an
existing master; it does not materialize an instance.

Suggested fix: extend generic lifecycle mechanics with a cross-collection
materialization form, preferably through the existing generic operation model
rather than an italic- or cross-master-specific endpoint. It must preserve the
instance, attach the new master before dependent fields, copy the interpolated
layers, and return the same verified transaction evidence.

Acceptance test: materialize Thin, Black, Regular Condensed, and Regular
Extended from their exact enabled static instances in one transaction, produce
the intended nine-master order, preserve all 29 instances and unrelated font
state, and require no staged Python.

## Recommended implementation order

1. Fix aggregate empty-layer transform semantics and add the live-shaped
   fixture test.
2. Add cancellation propagation and nonblocking runtime-health reads before
   further performance work, so future profiling cannot strand the server.
3. Instrument every preview phase, then profile the cold baseline and
   main-thread tuple iteration with the live 422-glyph fixture.
4. Make cached canonical/entity indexes survive failed previews and eliminate
   repeated whole-font enumeration.
5. Add generic static-instance materialization if five-to-nine Roman setup is
   part of the no-Python release gate.
6. Rerun the exact layer-target reference transaction; do not accept the
   shape/anchor workaround as the final workflow.

---

## 2026-08-31 restarted five-master end-to-end retest

### Outcome

The same runtime was retested after restarting Glyphs 4.0.1 build 4004 and
opening a fresh 423-glyph, five-master disposable `Dactylotype` package. This
run exercised the requested sequence rather than starting from the saved
nine-master Roman source:

1. make Black Condensed spacing and kerning 25% tighter than Regular;
2. materialize the four missing Roman cross masters and rebuild the 27-position
   matrix;
3. construct a first italic plane using registered `ital=1`, a positive
   12-degree Glyphs source angle, and a baseline-pivot shear.

The live document now contains the requested result and remains deliberately
unsaved:

| Property | Initial | Final |
|---|---:|---:|
| Masters | 5 Roman | 9 Roman + 9 italic |
| Instances | 29 | 29 |
| Glyphs | 423 | 423 |
| Black Condensed spacing mismatches | n/a | 0 |
| Black Condensed kerning mismatches | 111 changed pairs | 0 of 122 |
| Incompatible glyphs across 18 masters | n/a | 0 |
| Save calls | 0 | 0 |

The final live fingerprint is
`sha256:f55cda4e1532b5f9cca2212a9181f1b10f4d24d7aaf1f12ceede3163e336cc04`.
The source-file fingerprint observed during the last verified apply remained
`sha256:3ccfeeaf30c2d38ed14b2df93897bf2239a6ba61e0c7060ca2ce3cda05e39eab`.

This is a functional pass for the disposable font, but not a no-fallback
plugin pass. Generic mechanics completed the kerning edit and the final
component correction. Spacing, instance-to-master materialization, and the
structural italic construction still required approval-bound native fallbacks.

### Abstraction scorecard

| Task | Generic immutable path | Staged-document path | Applied path |
|---|---|---|---|
| Black Condensed kerning | Pass | Not needed | Exact generic preview/apply |
| Black Condensed spacing | Blocked by native rounding/alignment replay | Blocked by archive-only shape positions with zero normalized mismatch | Guarded `live_open_world` |
| Four Roman cross masters | No cross-collection materialization operation | Blocked by 72 derived instance-interpolation fields with zero normalized mismatch | Guarded native `addAsMaster()` |
| Nine-master italic structure | Failed fast: duplicated targets had no selected geometry | Geometry completed, then nine `italicAngle` metric fields replayed as zero | Guarded native construction |
| Italic component correction | Expressible in the generic affine model but not conveniently from measured source matrices | Pass: exact semantic preview | Stored staged preview applied without rerunning Python |

No task-specific endpoint is warranted. The missing abstractions are generic:
cross-collection materialization, complete master duplication, derived-state
normalization, and bounded affine field synthesis.

### 1. Black Condensed spacing and kerning

The final policy is exactly 75% of Regular:

- 142 layers use rounded Regular left and right bearings;
- 281 layers use rounded Regular advance only because they are empty,
  component-aligned, or tabular;
- the width-only set contains 86 empty layers, 172 component-configured layers,
  and 23 tabular layers (categories overlap);
- eight negative target bearings are preserved as valid design evidence;
- all 122 Black Condensed kerning pairs share Regular's pair domain and equal
  the rounded 75% value.

The generic kerning transaction was the strongest result in the run:

| Phase | Result | Time |
|---|---|---:|
| Preview 111 changed pairs | Applicable | `2.153s` client |
| Apply stored preview | 111 changes, one transaction | `2.751s` client |
| Full spacing + kerning readback | 0 spacing and 0 kerning mismatches | `17.059s` client |

The spacing path exposed three distinct verifier problems:

1. A 55.008-second generic preview produced 519 requested-effect mismatches
   from automatic component positioning.
2. Two 51–53-second variants still produced 202 node-coordinate mismatches
   because native grid normalization was compared with the requested floating
   coordinate rather than the normalized semantic result.
3. The final staged spacing candidate was rejected after 54.798 seconds for
   48 native archive `pos` differences even though it reported
   `normalizedMismatchCount=0` and `maximumAbsoluteDelta=0.0`.

The guarded spacing fallback itself took 3.197 seconds server-side and changed
all 423 eligible master layers. One earlier approval-bound call used stale
truncated master IDs and raised before the first intended assignment, yet the
server reported 4,986 observed changes and a changed fingerprint. Its
recovery-only `revert_change` then failed with `UnboundLocalError` in 2.298
seconds. The subsequent exact-ID preflight and idempotent retry completed
successfully.

#### Spacing/kerning optimization

1. Preserve requested fractional geometry exactly. Permit only registered,
   explicitly requested component-alignment effects during semantic comparison.
2. If canonical semantic comparison reports zero mismatches and zero numeric
   delta, do not reject solely because private archive positions differ.
3. Expose a compact result summary without materializing every normalized
   operation and constraint in `get_operation`.
4. Make a failed recovery terminally exact; the current recovery path cannot
   itself fail with an unclassified local-variable exception.
5. Keep pair-domain kerning operations on the typed path: it was fast,
   auditable, reversible, and needed no Python fallback.

### 2. Roman designspace repair and 27-position rebuild

The four authoritative static instances were materialized as masters at:

- Thin Normal: `100, 100, 0`;
- Regular Condensed: `400, 75, 0`;
- Regular Extended: `400, 125, 0`;
- Black Normal: `900, 100, 0`.

The live grid now contains all nine `wght` × `wdth` Roman corners. Every one of
the 27 static matrix instances has `manualInterpolation=false`; master
positions use one contributor, intermediate positions use the expected two
row masters, the disabled `Regular2` uses four contributors, and every weight
sum is 1.0.

Before materialization, full outline/component/anchor/advance signatures for
all 27 statics took 38.300 seconds, including 21.824 seconds of instance
interpolation. The staged four-master candidate took 25.580 seconds and was
rejected for 72 derived `instanceInterpolations` archive fields despite zero
normalized semantic mismatches. The approval-bound native materialization
took 3.708 seconds and created 2,124 observed changes.

Rebuilding the 27 source-level statics after repair took 45.948 seconds. All
positions produced 423 glyphs, 656 shapes, and 4,689 nodes. Compared with the
frozen five-master outputs, 11 signatures were unchanged and 16 changed; this
is expected impact from replacing the sparse interpolation surface.

Compiled acceptance was also attempted:

- `preview_export` failed in 336ms with `native_renderer_unavailable`;
- the documented `GSInstance.generate()` example uses capitalized keyword
  names, but Glyphs 4 requires lowercase names;
- the native exporter returns `None` on success although the bundled docs say
  it returns `True` or an error;
- 27 statics plus one variable TTF generated in 5.738 seconds;
- 27 statics plus one CFF2 variable generated in 6.749 seconds.

The CFF/CFF2 comparison makes the original position-level result explicit.
The five-master source had five exact master coordinates and therefore 22
non-exact corresponding statics. The repaired source has nine exact master
coordinates and 18 non-exact intermediate statics. Those 18 use the correct
new source weights but differ after separate static and variable compilation
by integer/charstring quantization, with a maximum sampled coordinate delta of
14 units. Four `four` variants, and `Delta` in some heavy positions, also use a
different compiled charstring topology. This is compiled-output evidence, not
a source master-compatibility failure.

#### Designspace optimization

1. Add a generic materialization operation that turns any exact static
   instance into a master while preserving the instance and returning a normal
   immutable preview. It must not be a Dactylotype- or cross-master-specific
   endpoint.
2. Treat automatic `instanceInterpolations` as derived state. Bind the axis
   coordinates and source master identities, then compare recomputed weights
   semantically.
3. Restore the explicit export renderer so compiled acceptance can use
   `preview_export`/`apply_export` instead of approval-bound native Python.
4. Correct the bundled `generate()` keyword casing and success contract.
5. Define compiled comparison tolerances by outline format: static TTF and
   variable TTF use different cubic-to-quadratic point layouts, while CFF/CFF2
   gives the meaningful contour-level comparison.

### 3. Italic first pass

The final plane uses the registered-axis model recommended in the earlier
review:

- Roman masters at `ital=0`;
- italic masters at `ital=1`;
- `italicAngle=12` on all nine italic masters;
- baseline pivot `y=0` and shear factor
  `0.2125565616700221`;
- one-unit grid snapping for nodes, anchors, component positions, and advances;
- live components retained and conjugated through the shear;
- all italic components explicitly positioned to prevent automatic alignment
  from undoing noncommuting affine transforms.

The live construction covered:

| Evidence | Result |
|---|---:|
| Italic masters | 9 |
| Target layers | 3,807 |
| Path nodes | 42,201 |
| Anchors | 1,539 |
| Components | 3,915 |
| Node mismatches | 0 |
| Anchor mismatches | 0 |
| Width mismatches over 0.5 grid unit | 0 |
| Topology mismatches | 0 |
| Incompatible glyphs | 0 |
| Italic kerning mismatches | 0 across 9 × 122 pairs |

The generic reference preview failed in 2.852 seconds with
`transform target contains no selected geometry`. This is much faster and
safer than the previous 147-second failure, but it proves that generic master
duplication still does not provide usable duplicated layers for the transform.

The complete grid-aware staged construction took 54.964 seconds. It executed
and self-validated the full 18-master candidate, then rejected nine derived
italic-angle metric records: expected 12, replay observed zero. Again, the
result reported zero normalized mismatches and zero maximum numeric delta.
The guarded live construction then completed in 12.014 seconds.

Direct six-value component transform assignment preserved topology but left
546 linear representation mismatches. A second staged pass used the generic
affine decomposition convention—position, signed scale, rotation, and
horizontal slant—to correct all 3,915 components:

| Phase | Result | Time |
|---|---|---:|
| Component semantic preview | 699 canonical changes, exact replay | `40.290s` |
| Apply stored preview | One verified transaction | `12.423s` |
| Final detached component audit | 0 mismatches | `44.375s` |

The maximum unavoidable reconstructed matrix delta is
`0.000017443076872356586`, below the `0.00002` acceptance tolerance.

#### Italic optimization

1. Complete generic master duplication so it copies all owned layers and every
   kerning direction before a following transform resolves its targets.
2. Synchronize authored `italicAngle` with Glyphs' derived italic-angle metric
   during replay; the current verifier still observes nine false zeroes.
3. Reuse the plugin's deterministic affine decomposition in the native adapter
   rather than assigning arbitrary six-value component tuples.
4. Permit an explicitly scoped staged-document diff. The component correction
   changed 699 canonical fields, but each preview/readback still cloned and
   compared the full 18-master, 423-glyph document.
5. Keep the registered `ital=0/1` coordinate independent from the positive
   12-degree Glyphs source angle. A degree-valued continuous slope belongs on
   a mapped `slnt` axis instead.

### Timing and cache observations

The restarted runtime preserved its strongest optimization: fingerprint-keyed
canonical reuse. The first axes read took 23.55 seconds; cached master,
instance, and font reads took 0.11–0.17 seconds. A paginated full-master layer
read took about 7.7–7.9 seconds. After the document grew to 18 masters, focused
detached audits still took about 44.4 seconds because clone capture and full
canonical comparison dominated even when the analysis itself was small.

The major remaining performance opportunity is therefore not network or JSON
transport. It is reusing an immutable canonical/native snapshot across a
task's preview, apply, and validation phases, and constraining native replay to
the exact impacted masters/layers while retaining full-document safety proofs.

---

## 2026-08-31 post-P0 reviewed-build comparison

### Gate result

The M1-M3 reviewed build was installed and Glyphs was restarted before this
comparison. The runtime reported API 2.0, Glyphs 4.0.1 build 4004, Python
3.14.6, runtime ID `2.0.0+0c53b4921c64`, and code hash
`0c53b4921c646ecce4c32acd844045b12130d94f088b37148092e4305c5450bf`.

The test used a new pristine five-Roman-master, 29-instance, 423-glyph
disposable. Its untouched package and two working copies have source
fingerprint
`sha256:3ccfeeaf30c2d38ed14b2df93897bf2239a6ba61e0c7060ca2ce3cda05e39eab`.
The previous unsaved 18-master document was preserved separately before the
restart.

P0 materially improved cancellation, empty-member handling, terminal
receipts, health responsiveness, and preview time. The post-P0 gate is still a
partial failure: spacing apply/recovery, generic materialization, composable
master duplication, and exact affine revert remain P1 blockers. No source save
was performed.

| Measure | Original report | Post-P0 result |
|---|---:|---:|
| Empty layer in collection transform | Typed failure at `147.406s` | 1,999 empty/no-op layers skipped; preview succeeded |
| Timed-out preview occupation | `>600s` and restart | Cancelled receipt in about `295ms` after notification |
| Health read during cancellation | Timed out behind preview | `38ms` observed |
| Cancelled live fingerprint | Not available | Exact unchanged fingerprint |
| Strict spacing preview | `55.008s`, 519 mismatches | `16.092s`, applicable; 422 resolved, 421 changed, 1 skipped |
| Strict italic structural attempt | `147-600+s` | Typed detached failure in `12.889s`; live fingerprint unchanged |
| Operation receipt after failure | Incomplete | Authoritative operation ID, terminal class, stage timings, and rollback evidence |

The explicit cancellation probe targeted a large detached preview. MCP
`notifications/cancelled` reached operation
`op_a2c496dba074441a9c382f9cbf016b0f`, which terminated as `cancelled` in
545ms total. The notification was sent after 250ms, so observed cancellation
latency was about 295ms. The live fingerprint remained
`sha256:27180f61b3df9b2c1957b53201e36ce3ae59cf950327c67b6d2f8d6e89b59f71`.

### Strict generic track

No Python fallback was used in this track.

| Task | Result | Evidence |
|---|---|---|
| Black Condensed kerning | Pass | 111 changed pairs; preview `3.994s`, apply `2.644s` |
| Black Condensed spacing | Preview pass, apply fail | Preview `16.092s`; apply failed after `17.736s`, then rollback was classified indeterminate |
| Four cross masters | Contract blocker | `materialize` was rejected by the generated transport union before planning |
| Nine-master italic first pass | Safe typed failure | Duplicate-plus-transform failed in `12.889s` because detached native duplication exposed 18 layers where replay expected the nine-layer baseline; no live mutation |

The failed spacing apply left 5,398 residual changes despite attempting
rollback. Restarting Glyphs without saving restored the clean five-master
source. This is a narrower and much faster failure than the original run, but
it confirms that the recovery path must be made exact before a generic spacing
apply can pass the release gate.

### Outcome track

Guarded fallbacks were used only for abstractions explicitly deferred to P1.
The successful task-level fallback count was three: spacing, instance-to-master
materialization, and italic construction.

Black Condensed spacing and kerning again finished with zero policy
mismatches across 423 layers and all 122 kerning pairs. Spacing used rounded
75% Regular bearings for 142 outline layers and rounded 75% Regular advance
for the 281 empty, component-configured, or tabular layers. The guarded
spacing mutation took `4.036s`; the source file remained unchanged.

The four missing Roman masters were materialized in `4.105s`, producing the
complete 3 x 3 Roman grid with no incompatible glyphs or missing master
layers. Rebuilding all 27 matrix positions took `47.512s`. Every position
contained 423 glyphs, 656 shapes, 4,689 nodes, and 1,171 anchors; exact masters
used one contributor, intermediate positions used two, and all contributor
weight sums were exactly 1. Compared with the frozen sparse five-master
signatures, 16 positions were unchanged and 11 changed in this run.

The guarded italic first pass was first proven on a detached clone, then
applied live in `16.675s`. It produced nine italic masters and retained all
29 instances and 423 glyphs. Validation covered 3,807 layers, 42,201 nodes,
1,539 anchors, and 3,915 components with zero width, topology, compatibility,
component, or italic-kerning mismatches. Deterministic component decomposition
had maximum native round-trip delta `1.1368683772161603e-13`; separate grid
position quantization was at most 0.5 unit.

Before the final affine benchmark the outcome fingerprint was
`sha256:cf50341bf30e7233d8b0e6981cd5cbd03279615601a8a91c3fd59dc0abf2e822`.
Counts were 18 masters, 29 instances, and 423 glyphs.

### All-nine Roman affine benchmark

One generic one-unit affine translation selected all nine Roman master-layer
collections, including empty layers:

| Phase | Result | Time |
|---|---|---:|
| Preview | Pass; 3,839 resolved, 1,840 changed, 1,999 skipped | `47.525s` |
| Stored apply and validation | Pass; canonical semantic equivalence | `28.791s` |
| Stored revert simulation | Fail before live revert; 292 component-derived width mismatches | `101.081s` |

The apply produced fingerprint
`sha256:74f4b71bd05fa37e1b2f57cf94a9f5f5335db68e2d4819daa2c9cd4db96a10e6`.
The exact revert gate then rejected the detached inverse because Glyphs
recomputed 292 widths on automatically positioned component glyphs; nothing
was reverted. The intended restoration fingerprint was the earlier `cf5034...`
value, while detached replay observed `338b3e...`. The live document remains
unsaved at `74f4...`; the working package bytes are still the untouched
five-master source and there were zero save calls.

This historical failure helped define the next abstraction work: one shared
precision scope must prevent grid normalization, while semantic equivalence
owns only explicit component positioning, machine-scale affine round trips,
derived interpolation, and italic-angle metrics. Exact recovery must retain enough authoritative native evidence
to restore the pre-operation fingerprint rather than merely accept a visual
inverse.
