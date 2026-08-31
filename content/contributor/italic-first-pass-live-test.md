# Nine-master first-italic-pass live test

## Result

On 2026-08-30, Glyphs MCP 2.0.0 was tested against the open disposable
`Dactylotype` source in Glyphs 4 build 4004. The requested 12-degree first
italic pass is **blocked at final application**, not complete and not saved.

The intended construction is fully resolved:

- positive 12-degree Glyphs source angle;
- baseline pivot at `y=0`;
- one-unit grid snapping;
- original advance widths and origins preserved;
- all 422 glyphs and 29 instances preserved;
- nine new italic bootstrap masters at the matching weight/width locations;
- live components retained, with affine transforms conjugated through the
  shear;
- anchors and path nodes transformed with their source layers;
- source topology and all master compatibility preserved.

The open document currently contains an **unsaved 18-master residual state**
left by a failed verified transaction whose rollback also failed. All later
experiments were detached and did not change that live state. The source on
disk is still the last saved nine-master Roman grid, with source-file
fingerprint
`sha256:180664018e2ab383234310823db466f7d2d4fd95d196c85badd3ba34ee0a0c73`.
The residual live-document fingerprint used by the last safe attempt is
`sha256:5c84e6e14bdf65cfc82c49049f2f8686e36500a9df7ab4a3323727616e0c6559`.

No save was attempted. Completing the live mutation now requires explicit
approval for a recovery-only `live_open_world` edit, because that path cannot
offer atomic rollback. The safety gate correctly rejected it without that
additional approval.

This report records the original 2.0.0 run. The v2 remediation described at
the end replaces that recovery-only workaround with generic declarative
mechanics. It is covered by automated tests here but still requires a fresh
disposable-font live release gate; the quarantined residual document is not a
valid retest source.

## Resolved design evidence

The nine Roman-to-italic master pairs are:

| Roman source | Italic target | Location (`wght`, `wdth`, `ital`) |
|---|---|---|
| Thin Condensed | Thin Condensed Italic | `100, 75, 12` |
| Thin | Thin Italic | `100, 100, 12` |
| Thin Extended | Thin Extended Italic | `100, 125, 12` |
| Regular Condensed | Regular Condensed Italic | `400, 75, 12` |
| Regular | Regular Italic | `400, 100, 12` |
| Regular Extended | Regular Extended Italic | `400, 125, 12` |
| Black Condensed | Black Condensed Italic | `900, 75, 12` |
| Black | Black Italic | `900, 100, 12` |
| Black Extended | Black Extended Italic | `900, 125, 12` |

The complete detached rehearsal covered 3,798 target layers, 42,417 path
nodes, 1,539 anchors, and 3,879 components. It found:

- zero missing layers;
- zero path/component correspondence mismatches;
- zero explicit component-master references;
- zero component cycles;
- zero width mismatches;
- zero topology/signature mismatches;
- zero Glyphs-native compatibility failures;
- 2,826 source components using automatic alignment;
- 1,053 source components already positioned explicitly;
- 87 automatically aligned transforms that do not commute with a shear
  because they are reflected or asymmetrically scaled;
- a maximum unavoidable component-linear representation difference of
  `0.000012344902873352541` units after Glyphs decomposition.

The verifier cannot currently replay this semantically valid result. Keeping
automatic alignment produced 400 archive mismatches from Glyphs' automatic
repositioning and grid snapping. Making every italic component explicit and
snapping both coordinates reduced the mismatch first to 14, then to seven.
Those last seven are only `angle`/`slant` double-normalization differences of
about `7e-15`, but native archive equivalence treats them as exact failures.

## Timing

Wall-clock timing started at 13:10:55 EDT. The first complete blockage report
was produced at 14:18:13 EDT, after **67m 17.878s**. Fast metadata calls are
included because the requested test is intended to expose total interaction
cost, not only font-processing time.

| # | Step | Status | Wall time |
|---:|---|---|---:|
| 1 | Preflight: server, runtime, open document | pass | 0.125s |
| 2 | Knowledge search: slant, transforms, components, italic angle | pass | 0.129s |
| 3 | Knowledge refinement: APIs and angle semantics | pass | 0.109s |
| 4 | Knowledge retrieval: authoritative entries | pass | 0.064s |
| 5 | Canonical inspection: document, axes, masters | pass | 17.129s |
| 6 | Knowledge search: safe master duplication | pass | 0.116s |
| 7 | Detached probe: duplication and component risk | error: undocumented output ceiling | 5.893s |
| 8 | Retry detached probe within output limits | pass | 39.318s |
| 9 | Knowledge search: geometry mutation and compatibility APIs | pass | 0.129s |
| 10 | Detached rehearsal: one full italic master | pass: exposed empty copied layers | 44.467s |
| 11 | Knowledge search: explicit layer duplication | pass | 0.121s |
| 12 | Detached rehearsal retry: explicit layers and kerning | pass | 46.634s |
| 13 | Stage atomic nine-master italic construction | error: italic metric replayed as zero | 112.079s |
| 14 | Retry stage with insertion-complete master metadata | error: pre-attach axis/metric setters | 15.128s |
| 15 | Retry stage: preinsert italic metric, postinsert axes | error | 14.644s |
| 16 | Detached probe: preattach copied master | pass | 33.609s |
| 17 | Retry stage: preattached insertion-complete masters | error: italic metric replayed as zero | 111.329s |
| 18 | Stage workaround: masters and geometry, defer italic metric | pass: immutable preview created | 111.366s |
| 19 | Apply immutable nine-master geometry preview | error: verification and rollback both failed | 48.037s |
| 20 | Emergency audit after failed apply/rollback | pass | 7.315s |
| 21 | Residual-state audit: geometry, layers, kerning | pass | 58.895s |
| 22 | Stage canonical recovery transform on existing italic masters | error: residual was already partly sheared | 17.606s |
| 23 | Residual classification: Roman vs sheared vs other | pass | 138.039s |
| 24 | Focused canonical read: residual A geometry | warning: parent selector returned no useful layer data | 6.751s |
| 25 | Focused numeric audit: A residual coordinates | pass | 52.933s |
| 26 | Stage idempotent corrected italic construction | error: automatic component moved by one unit | 21.040s |
| 27 | Detached probe: automatic component setter behavior | pass | 51.507s |
| 28 | Stage corrected construction with auto-component safety | error: arbitrary affine setter normalized transform | 25.307s |
| 29 | Detached probe: normalized nonautomatic component transform | pass | 51.581s |
| 30 | Detached probe: `hungarumlautcomb` internal transform | pass | 51.511s |
| 31 | Detached probe: exact component affine decomposition | pass | 52.584s |
| 32 | Stage exact decomposed-component italic correction | error: native precision exceeded `1e-6` | 22.847s |
| 33 | Detached probe: reflected K component decomposition | pass | 51.646s |
| 34 | Detached probe: all K component decompositions | pass | 52.406s |
| 35 | Stage exact correction with native component tolerance | error: another master exceeded `1e-5` | 27.786s |
| 36 | Global component representation and auto-alignment audit | error: stale native Roman master IDs | 22.499s |
| 37 | Global component audit using resolved master names/IDs | pass | 56.202s |
| 38 | Grid-snapped component recovery precision audit | pass | 57.004s |
| 39 | Stage deterministic complete correction | error: policy rejected harmless `set.remove()` | 4.064s |
| 40 | Retry complete correction with policy-safe cycle check | error: 300-second tool timeout | 303.092s |
| 41 | Verify live document after staging timeout | pass | 33.480s |
| 42 | Stage Thin Condensed Italic as a scoped preview | error: delayed fingerprint normalization made baseline stale | 9.132s |
| 43 | Re-read live state after stale baseline | pass | 0.188s |
| 44 | Retry scoped preview on rebased state | error: `copy` import policy | 19.256s |
| 45 | Request reviewed live fallback | blocked by safety gate | 4.221s |
| 46 | Retry scoped preview without unsupported imports | error: `axesValues` is read-only in raw detached API | 18.723s |
| 47 | Probe attached target `axes` accessor | error: raw selector is not iterable | 17.640s |
| 48 | Probe attached target `axesValues` accessor | error: raw selector is not iterable | 17.677s |
| 49 | Stage through native axis IDs | error: 400 native archive mismatches | 60.614s |
| 50 | Stage explicit components and full grid snap | error: 14 sub-picounit archive mismatches | 63.810s |
| 51 | Stage one native-settle pass | error: seven `~7e-15` archive mismatches | 60.344s |
| 52 | Stage fixed-point native settle | error: same seven `~7e-15` archive mismatches | 62.236s |

## Blockage log

1. **P0 — failed apply can leave a corrupted live residual.** Applying preview
   `preview_6330d477e6a24e49891c2c2ff317a5aa` failed verification with
   `axis requires unique non-empty canonical entity IDs`; rollback also failed,
   returned `stateMayHaveChanged=true`, and left 18 unsaved masters in the open
   font. The source file remained unchanged, but atomicity was lost.
2. **P0 — inserting an italic master drops its italic-angle metric during
   replay.** Every structural stage that inserted masters with angle 12 failed
   a native archive comparison at `metric:9`: expected 12, observed 0.
3. **P0 — native replay requires bitwise float equality.** Seven valid
   component `angle`/`slant` values still fail with differences around
   `7e-15`. Repeated native read/write settling does not converge to the
   verifier's expected serialization.
4. **P0 — native side effects are compared against pre-side-effect semantic
   values.** Automatic component alignment and Glyphs grid snapping caused 400
   mismatches even though direct and replayed documents were typographically
   equivalent.
5. **P1 — a full-document preview exceeds the transport deadline.** The
   asserted nine-master correction spent more than 300 seconds in clone,
   archive, canonical comparison, and replay verification, then timed out
   without returning a preview.
6. **P1 — detached master identity is unstable after rollback.** The failed
   apply changed all nine Roman native master IDs, invalidating exact IDs read
   earlier in the same task. Name-based resolution was required to recover.
7. **P1 — copied masters do not include usable master layers or kerning.** A
   copied/attached `GSFontMaster` yielded 422 empty target layers and no copied
   kerning. Every layer and all three kerning directions had to be copied
   manually.
8. **P1 — detached execution exposes inconsistent Python/SDK surfaces.** The
   `copy` standard-library import was accepted by one long stage and rejected
   by a scoped retry. `GSFontMaster.axesValues` appeared as a raw read-only
   selector rather than the documented wrapper proxy, requiring native
   axis-ID setters.
9. **P1 — the policy scanner rejects harmless collection methods.** A local
   graph traversal's `set.remove()` was rejected as a staged policy violation,
   even though it could not remove font data.
10. **P1 — component transforms have no typed affine operation.** Correctly
    conjugating a component transform through a shear required reverse-
    engineering the raw six-value tuple and decomposing it into scale,
    rotation, slant, and position. Direct transform assignment normalized the
    matrix incorrectly for rotated components.
11. **P1 — automatic-component replay is not semantic.** Reflected and
    asymmetrically scaled automatic components do not commute with a shear;
    87 of 2,826 automatic components required explicit treatment. The plugin
    provides no diagnostic or safe conversion helper.
12. **P1 — canonical selectors omit decisive data.** Master collection index
    and axis values were unavailable in ordinary reads, and a parent-scoped
    layer query returned no useful entities.
13. **P2 — output limits remain undiscoverable.** The callable schema permits
    arbitrary `maxOutputChars`, while the implementation rejects values above
    8192.
14. **P2 — timing is not first-class.** Total task timing had to be assembled
    externally from 52 calls; the plugin does not provide an end-to-end phase
    trace or reusable stable snapshot across related checks.

## v2 remediation and maintainer acceptance

### P0 — transaction and equivalence correctness

Implemented:

1. The transaction kernel now records `stable → applying → committed/restored`
   and quarantines `indeterminate`. A failure is classified as exact committed,
   exact restored, or indeterminate; the last state rejects every later edit.
2. Snapshot-backed recovery is a bounded transaction mode, not an unsafe-write
   bypass. Its preview binds the exact canonical and source fingerprints;
   apply requires `confirmRecovery=true`, creates and fingerprints one full
   native snapshot, and returns a recovery receipt.
3. Registered semantic equivalence is the default. It accepts reviewed
   omission defaults, identity-addressed storage order, derived grid/alignment
   effects, and bounded component-decomposition round trips. The observed
   `~7e-15` angle/slant deltas pass with evidence; unknown private state and
   one-unit geometry changes still block. `strict_archive` remains available
   as the deliberately expensive diagnostic gate.
4. Master replay synchronizes nonzero `italicAngle` with the native italic-
   angle metric, attaches a new master before axes/metrics, and uses tested
   wrapper, native mutable-copy, keyed-archive, and Python-copy fallbacks.

Acceptance checks: fault injection during apply, verification, rollback, and
restore must end exact committed, exact restored, or quarantined; nonzero
italic-angle metrics survive duplicate/apply/revert; semantic `7e-15` deltas
pass and strict mode blocks them.

### P1 — generic fast mechanics

Implemented without italic-specific endpoints:

1. Consecutive generic `duplicate` operations batch all nine masters in one
   structural pass. Each duplicate owns every master layer and LTR, RTL,
   vertical, and contextual kerning. Shard-backed canonical snapshots retain
   unchanged glyph data across planning and validation.
2. Generic `transform` accepts CoreGraphics-order matrices, an optional pivot,
   exact or grid quantization, selected paths/anchors/components, component
   prepend/append/conjugate/unchanged composition, and explicit alignment
   policies. It supports layer, path/component shape, node, and anchor targets,
   preserves live component references, rejects unsupported shapes and
   singular conjugation, and disables automatic alignment only for requested
   noncommuting transforms.
3. `collection.index`, parent-scoped layer reads, axes, alignment, and
   component transforms are available through ordinary projections.
4. Preview/apply return stage timings, equivalence evidence, bounded normalized
   paths and numeric deltas, rollback classification, and recovery evidence.

The reference pass is now one immutable operation list composed of
`duplicate`, `move`, `set`, and `transform`, using a baseline pivot,
`componentComposition=conjugate`, `alignmentPolicy=explicit_noncommuting`, and
the selected grid policy. Staged Python is only an unsupported-capability
fallback.

Acceptance checks: one semantic preview, one atomic apply, one validation read,
no Python, unchanged widths/origins/topology/coverage/instances/mappings, all
42,417 nodes, 1,539 anchors, and 3,879 live components transformed, and total
read/preview/apply/validation time below 120 seconds.

### Before/after timing gate

| Measurement | Before (2.0.0 live run) | Required after remediation |
|---|---:|---:|
| Calls before final blockage | 52 | 4 logical phases |
| End-to-end time | 67m 17.878s | < 120s |
| Full preview | > 300s timeout | bounded immutable preview |
| Python stages | required repeatedly | 0 |
| Live applies | 1 failed/mixed | 1 exact committed or exact restored |

The after column is the live release criterion, not a claimed measurement.
Run it only on a fresh disposable copy of the saved nine-Roman-master source;
do not reuse the residual 18-master document.
