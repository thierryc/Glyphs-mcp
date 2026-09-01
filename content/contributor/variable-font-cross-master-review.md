# Variable-font cross-master and italic-axis review

> Historical measurement: coordinate snapping and grid-normalization advice in
> the recorded run is superseded. Current v2 execution preserves floating-point
> geometry centrally, leaves global automatic alignment unchanged, and rejects
> native grid rounding as requested-effect mismatch.

## Outcome

On 2026-08-30, Glyphs MCP 2.0.0 was tested against the disposable
`Dactylotype` source in Glyphs 4 build 4004.

The review now covers two distinct states:

| State | Masters | Slope locations | Persisted | Verdict |
|---|---:|---|---|---|
| Saved source | 9 | `ital=0` | Yes | Roman `wght` × `wdth` source grid passes |
| Open residual | 18 | `ital=0`, `ital=12` | No | Unsafe transaction residual; review evidence only |
| Intended source | 18 | Roman plus one italic plane | No | Blocked pending recovery and axis-semantics decision |

The four missing Roman cross masters were successfully materialized from their
authoritative static instances and saved. The later attempt to populate the
italic axis across all nine weight/width positions did not complete safely: a
verified apply failed, rollback also failed, and Glyphs was left with an
unsaved 18-master residual. The saved nine-master source remains intact.

Overall status:

- **PASS** — saved Roman `wght` × `wdth` design space and source-level static
  interpolation.
- **BLOCKED** — new italic plane, persistence, and cross-slope interpolation.
- **SKIP** — compiled variable-font tables and application behavior, because
  no variable binary was produced or inspected.

The detailed italic construction, timing, replay failures, and implementation
tasks are recorded in
[italic-first-pass-live-test.md](./italic-first-pass-live-test.md).

## Axis model

The source declares `wght`, `wdth`, and `ital`, in that order.

| Axis | Observed source range | Origin/default intent | Mapping | Review |
|---|---|---|---|---|
| Weight (`wght`) | 100–900 | Regular, 400 | None | Pass |
| Width (`wdth`) | 75–125 | Normal, 100 | None | Pass |
| Italic (`ital`) | Saved: 0 only; residual: 0–12 | Roman, 0 | None | Blocked |

The saved source projects null axis `default` fields and uses an explicit
Variable Font Origin pointing to Regular,
`0578215A-7423-43EB-8AD4-4C95A1C78DFA`. No Axis Mappings custom parameter was
present in the reviewed source.

### Italic-axis semantic decision

The first-pass experiment used a positive 12-degree Glyphs source lean and
placed the bootstrap masters at `ital=12`. Those are different concepts:

- a registered OpenType `ital` axis conventionally distinguishes Roman and
  italic with coordinates `0` and `1`;
- the Glyphs master `italicAngle` can remain positive 12 degrees for the source
  construction;
- a continuous degree-valued slope axis would conventionally use `slnt`, with
  exported right-leaning values using the opposite sign.

Therefore, `ital=12` must not be accepted as production-ready merely because
the source geometry leans by 12 degrees. Before saving the new plane, choose
one of these models:

1. Keep the registered `ital` axis, move the italic masters to `ital=1`, and
   retain `italicAngle=12` on those masters. This is the recommended model for
   a Roman/Italic switch.
2. Replace or supplement it with a continuous `slnt` axis and define explicit
   internal/external mappings between Glyphs' positive source angle and the
   exported slope coordinates.

Until that choice is implemented and reviewed, the new axis is **BLOCKED**
independently of the plugin transaction failures.

## Saved Roman plane

The saved master order is weight-major, with width increasing within each row.
All nine locations have `ital=0`.

| Weight | Condensed (`wdth=75`) | Normal (`wdth=100`) | Extended (`wdth=125`) |
|---|---|---|---|
| Thin (`wght=100`) | Thin Condensed<br />`AF94AE23-1910-4859-814C-A48A47EEDF58` | Thin<br />`7E73421B-6AA8-45D6-8FD0-2BB7AFA6BE50` | Thin Extended<br />`926F7910-9E82-41CD-9117-571F75F96159` |
| Regular (`wght=400`) | Regular Condensed<br />`746A71CA-CDEA-4FAC-AD5F-4A26E9F19F27` | Regular<br />`0578215A-7423-43EB-8AD4-4C95A1C78DFA` | Regular Extended<br />`9E2F0698-1A9F-450E-85F3-6E750C8E862A` |
| Black (`wght=900`) | Black Condensed<br />`20B80D33-B5FE-4CBE-AB86-1B0C04FA398E` | Black<br />`E45ACACC-CE61-4304-BFB8-98D72C88CD9A` | Black Extended<br />`6825D31D-5B3D-46C4-B419-A0158C275CED` |

Thin, Black, Regular Condensed, and Regular Extended came directly from the
matching enabled static instances through Glyphs' native **Instance as
Master** API. No substitute source or detached geometry synthesis was used.

## Proposed italic plane

The failed construction created the following target records in the open,
unsaved document. They are listed to make the residual auditable; they are not
approved source masters.

| Weight | Condensed (`wdth=75`) | Normal (`wdth=100`) | Extended (`wdth=125`) |
|---|---|---|---|
| Thin (`wght=100`) | Thin Condensed Italic<br />`1EA9CCC2-9218-43D5-A8DA-9EF0DCCA9292` | Thin Italic<br />`43F81991-E402-44B5-8F2A-24D736847694` | Thin Extended Italic<br />`363A4511-8CA2-45C7-894B-DE958AB11A5A` |
| Regular (`wght=400`) | Regular Condensed Italic<br />`C68992DB-E3E7-4215-8C8A-CA75D9BD89B5` | Regular Italic<br />`CBB85BE6-9D1C-411C-B89A-8FE6BFF8AF63` | Regular Extended Italic<br />`17D9E5C1-9FE6-4F5C-80D4-946219A31EB1` |
| Black (`wght=900`) | Black Condensed Italic<br />`9366E589-8ED1-4263-87B9-52F7ED9BD0B7` | Black Italic<br />`8B281856-CA84-4487-9AB0-B8FBBF7CF3C7` | Black Extended Italic<br />`65901D5D-CBDA-4FB5-8EF9-F42DE2E21A9A` |

The intended first pass uses a baseline pivot at `y=0`, a positive 12-degree
source shear, one-unit grid snapping, unchanged advances/origins, transformed
anchors, and live component references. The residual does not reliably embody
that final specification because the transaction failed during verification
and rollback.

## Preservation evidence

### Saved baseline

The guarded Roman-grid operation compared bounded signatures before and after
the edit:

- all 29 instances remained in place with the same names, types, coordinates,
  export flags, visibility, weight classes, and width classes;
- all 422 glyphs retained their export flags and Unicode assignments;
- the glyph-coverage checksum remained `396100897`;
- there were no special layers before or after the Roman-grid edit;
- every glyph had exactly nine saved master layers;
- axes, custom parameters, Variable Font Origin, and absence of Axis Mappings
  were preserved.

The saved source fingerprint changed from
`sha256:0e973269eb0bb4496d508369475e101ec3a95c324730b54a9c8d2eeec57ca63b`
to
`sha256:180664018e2ab383234310823db466f7d2d4fd95d196c85badd3ba34ee0a0c73`.

### Italic rehearsal

Detached construction and recovery rehearsals covered the entire proposed
italic plane:

- 3,798 target layers;
- 42,417 path nodes;
- 1,539 anchors;
- 3,879 components;
- zero missing layers;
- zero path/component correspondence mismatches;
- zero explicit component-master references;
- zero component cycles;
- zero advance-width mismatches;
- zero topology/signature mismatches;
- zero Glyphs-native compatibility failures in the detached candidate.

Component handling is the decisive exception. Of 3,879 components, 2,826
used automatic alignment in the Roman sources, and 87 of those used reflected
or asymmetrically scaled transforms that do not commute with a shear. The
maximum unavoidable linear representation difference after native Glyphs
decomposition was `0.000012344902873352541` units.

This evidence proves that a compatible bootstrap candidate can be calculated.
It does not prove that the open residual matches that candidate, nor that the
candidate can be saved or exported safely.

## Source-level interpolation review

### Roman plane: pass

- Glyphs native `mastersCompatible` reported 0 incompatible glyphs out of 422.
- Master-layer coverage reported 0 errors out of 422 glyphs.
- All 28 static instances generated through `GSInstance.interpolatedFont`
  without error.
- Every generated instance contained all 422 glyphs.
- Every instance interpolation weight sum was exactly `1.0`; one to four
  masters contributed at the tested locations.
- The disabled `Regular2` instance at `wght=395`, `wdth=95`, `ital=0`
  interpolated successfully from four masters.

### Italic and cross-slope regions: blocked

- The 29 preserved instances remain on the Roman plane; no authoritative
  italic named instances were added or reviewed.
- No native static instance at the proposed italic endpoint was accepted from
  the final live state.
- No midpoint between Roman and italic was sampled.
- No `wght` × `wdth` interpolation sweep was accepted on the italic plane.
- The detached candidate reported compatible master structures, but the
  verified transaction could not reproduce or apply it.
- Kerning copies for LTR, RTL, and vertical directions were rehearsed, but
  their final residual and variable interpolation were not accepted.

The new axis therefore cannot inherit the Roman plane's interpolation pass.

## Instances, mappings, and special layers

- The source still has 29 instances. Their preserved review covers `ital=0`;
  it does not provide names or coordinates for an italic endpoint.
- No Axis Mappings custom parameter was present. Internal/external mapping for
  a production `ital` or `slnt` axis remains to be specified and verified.
- The explicit Variable Font Origin remains the Roman Regular master.
- No brace/intermediate or bracket/alternate layers were present in the saved
  review. The new plane uses full masters rather than virtual masters.
- No switching strategy was reviewed for glyphs that may eventually require
  structural italic alternates, such as single-storey forms.

## Compiled variable-font proof

The component-preserving source-bundle preview returned
`native_renderer_unavailable`. No compiled variable font was inspected or
produced.

Consequently, all of the following remain **SKIP**, not pass:

- `fvar` ranges, defaults, and named instances;
- `avar` mappings;
- STAT axis values and style linking;
- `gvar` or CFF2 outline variation;
- HVAR, VVAR, and MVAR metrics;
- GDEF and GPOS variation stores, including variable kerning;
- name IDs and style names;
- shaping, rasterization, and application behavior.

The unresolved `ital=12` semantics are an additional export blocker even if
the renderer becomes available.

## Plugin blockage summary

The Roman-grid task succeeded, but the complete Roman-plus-italic workflow
exposed these critical failures:

1. **P0 — verified apply and rollback are not atomic.** A failed italic apply
   returned `stateMayHaveChanged=true` and left an 18-master residual after
   rollback also failed.
2. **P0 — inserted italic angle is not replayed.** Structural previews wrote
   `italicAngle=12`, while native replay observed zero for the corresponding
   master metric.
3. **P0 — native equivalence is too strict for normalized component floats.**
   The final scoped preview was rejected for seven `angle`/`slant` differences
   around `7e-15`.
4. **P0 — derived native behavior is compared as authored state.** Automatic
   component alignment, grid snapping, and automatic instance interpolation
   caches produced replay mismatches even when semantic intent matched.
5. **P0 — export review cannot reach its renderer.** Source-bundle preflight
   fails with `native_renderer_unavailable`.
6. **P0 — save success can be reported as failure.** The earlier Roman-grid
   save wrote new source bytes but returned `save_verification_failed` because
   the expected notification was not observed.
7. **P1 — whole-font verification is too slow.** A complete italic preview
   exceeded the 300-second transport limit; the end-to-end italic attempt took
   67m 17.878s across 52 measured steps.
8. **P1 — master duplication is incomplete.** Copying a master produced empty
   target layers and no copied kerning, requiring manual duplication of every
   glyph layer and all kerning directions.
9. **P1 — canonical reads omit essential design-space evidence.** Stable
   master order and axis coordinates were unavailable through ordinary
   projections, and exact review required Python.
10. **P1 — detached Python and the Glyphs wrapper disagree.** Import policy and
    attached-master axis access differed across otherwise equivalent staged
    runs.

## Maintainer task list and acceptance

### P0 — implemented in v2, pending fresh live gate

1. **Transaction terminal-state proof.** Apply and rollback now end in exact
   `committed`, exact `restored`, or quarantined `indeterminate`. Further edits
   are refused only for the indeterminate state and return recovery guidance.
   Fault-injection acceptance covers apply, verification, rollback, and
   history failures.
2. **Bounded recovery.** `transactionMode=snapshot_backed_recovery` is bound to
   exact document and source fingerprints, requires `confirmRecovery=true`,
   creates one fingerprinted full native snapshot, and returns an opaque
   recovery receipt. It does not relax mutation or verification rules.
3. **Registered semantic equivalence.** Semantic verification is the default
   and accepts only reviewed defaults, identity-addressed ordering, explicitly
   requested component-alignment effects, and bounded IEEE-754 component decomposition.
   Unknown private fields and one-unit geometry differences block. Optional
   `strict_archive` retains the diagnostic byte-sensitive replay path.
4. **Complete master lifecycle.** Generic duplicate now copies every owned
   layer plus LTR, RTL, vertical, and contextual kerning, attaches the master
   before attachment-dependent values, and synchronizes `italicAngle` with its
   metric. Glyphs 3.5/4 wrapper, mutable-native, keyed-archive, and Python-copy
   fallbacks are covered.

Expected behavior: a failed operation never leaves an editable mixed state;
the observed `~7e-15` angle/slant normalization is accepted with a reported
delta in semantic mode and rejected in strict mode.

### P1 — generic cross-master workflow

No italic-specific or instance-as-master endpoint is introduced. One immutable
preview composes:

1. consecutive generic `duplicate` operations for the nine target masters;
2. generic `move`/`set` operations for final order and locations;
3. one generic `transform` over target layers using the baseline pivot,
   exact floating-point geometry, `componentComposition=conjugate`, and
   `alignmentPolicy=explicit_noncommuting`;
4. after-constraints and one validation read for coverage, widths/origins,
   topology, compatibility, kerning, axis locations, component references,
   alignment, and transforms.

The mechanics registry now exposes `collection.index`; ordered masters, axes,
parent-scoped layers, component alignment, and transforms no longer require
Python. Preview/apply return stage timings, equivalence evidence, normalized
paths and numeric deltas, rollback classification, and recovery evidence.

Acceptance checks:

- preserve all 422 glyphs, 29 instances, axes, mappings, Unicode coverage,
  widths, origins, topology, compatibility, and all kerning directions;
- create nine masters and 3,798 layers, transform 42,417 nodes, 1,539 anchors,
  and 3,879 live components;
- use no staged or open-world Python;
- complete cached read, semantic preview, atomic apply, and validation in less
  than 120 seconds;
- leave saving as a separate explicit action.

| Timing | Original live run | Release gate |
|---|---:|---:|
| End to end | 67m 17.878s | < 120s |
| Full preview | > 300s timeout | completes |
| Calls/stages | 52 | 4 logical phases |
| Python mutation stages | many | 0 |

### P1 — design-space decision still open

1. Choose registered `ital=0/1` or a mapped continuous `slnt` model before
   saving an italic plane. The current positive 12-degree source angle is not
   by itself a valid registered `ital` coordinate.
2. Add deliberate italic endpoint instances and at least one cross-slope proof
   position; validate names, uniqueness, bounds, and style linking.
3. Sweep `wght` × `wdth` at the endpoint and sample between Roman and italic;
   verify LTR, RTL, and vertical kerning interpolation.
4. Review glyphs requiring deliberate alternates rather than a
   topology-preserving mechanical slant.

### P2 — compiled variable-font acceptance

1. Restore the source-bundle renderer and reconcile successful Glyphs package
   saves independently of notification timing.
2. Produce a compiled variable binary only after the source is safely saved.
3. Validate `fvar`, `avar`, STAT, outline and metric variation tables, GDEF,
   GPOS variation stores, names, style linking, and representative application
   behavior.

The implementation work above is automated-test evidence. The timing and
Glyphs 3.5/4 compatibility claims remain release-gate requirements until run
on fresh disposable copies; the unsaved 18-master residual must not be reused.
