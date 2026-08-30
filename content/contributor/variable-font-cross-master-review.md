# Variable-font cross-master live test

## Result

On 2026-08-30, Glyphs MCP 2.0.0 was tested against the open disposable
`Dactylotype` source in Glyphs 4 build 4004. The requested four static
instances were materialized with Glyphs' native **Instance as Master** API and
the source was saved.

The resulting nine-master grid is weight-major, with width increasing within
each row:

| Weight | Condensed (`wdth=75`) | Normal (`wdth=100`) | Extended (`wdth=125`) |
|---|---|---|---|
| Thin (`wght=100`) | Thin Condensed<br>`AF94AE23-1910-4859-814C-A48A47EEDF58` | Thin<br>`7E73421B-6AA8-45D6-8FD0-2BB7AFA6BE50` | Thin Extended<br>`926F7910-9E82-41CD-9117-571F75F96159` |
| Regular (`wght=400`) | Regular Condensed<br>`746A71CA-CDEA-4FAC-AD5F-4A26E9F19F27` | Regular<br>`0578215A-7423-43EB-8AD4-4C95A1C78DFA` | Regular Extended<br>`9E2F0698-1A9F-450E-85F3-6E750C8E862A` |
| Black (`wght=900`) | Black Condensed<br>`20B80D33-B5FE-4CBE-AB86-1B0C04FA398E` | Black<br>`E45ACACC-CE61-4304-BFB8-98D72C88CD9A` | Black Extended<br>`6825D31D-5B3D-46C4-B419-A0158C275CED` |

All locations have `ital=0`. The four new designs came directly from the exact
enabled static instances named Thin, Black, Regular Condensed, and Regular
Extended. No detached geometry synthesis or substitute source was used.

## Preservation evidence

The guarded live script compared complete bounded signatures before and after
the edit and rejected any mismatch in axes, instances, font custom parameters,
or glyph coverage.

- Axes remain `wght`, `wdth`, and `ital`, in that order. The saved source again
  projects their original null `default` fields.
- The explicit Variable Font Origin remains the original Regular master,
  `0578215A-7423-43EB-8AD4-4C95A1C78DFA`.
- The font has no Axis Mappings custom parameter before or after the edit.
- All 29 instances remain in place with the same names, types, coordinates,
  export flags, visibility, weight classes, and width classes.
- The same 422 glyphs, export flags, and Unicode values remain. The baseline
  coverage checksum was `396100897`, and the post-edit signature matched it
  exactly.
- There were no special layers before or after the edit. Every glyph now has
  exactly nine master layers.

The persisted source fingerprint changed from
`sha256:0e973269eb0bb4496d508369475e101ec3a95c324730b54a9c8d2eeec57ca63b`
to
`sha256:180664018e2ab383234310823db466f7d2d4fd95d196c85badd3ba34ee0a0c73`.

## Variable-font review

Source-level interpolation passed:

- Glyphs native `mastersCompatible` reports 0 incompatible glyphs out of 422.
- Master-layer coverage reports 0 errors out of 422 glyphs.
- All 28 static instances generated through `GSInstance.interpolatedFont`
  without error.
- Every generated static instance contained all 422 glyphs.
- Every instance interpolation weight sum was exactly `1.0`; between one and
  four masters contributed at the tested locations.
- The disabled `Regular2` test instance at `wght=395`, `wdth=95`, `ital=0`
  also interpolated successfully from four masters.

The component-preserving source-bundle preview did not run because the active
plugin returned `native_renderer_unavailable`. Consequently, compiled `fvar`,
`avar`, STAT, `gvar`/CFF2, HVAR/VVAR/MVAR, GDEF, GPOS variation stores, name
IDs, and application behavior remain **SKIP**, not pass. No compiled variable
font was inspected or produced by this test.

## Plugin blockage log

The font task succeeded, but it required a live-open-world fallback and exposed
the following product defects or friction points.

1. **P0 — staged Instance-as-Master edits are rejected.** The detached edit
   completed and passed its own preservation and compatibility assertions, but
   final native-archive verification reported 72 mismatches under automatic
   `instances[*].instanceInterpolations`. Those values are derived caches when
   `manualInterpolation=false`; the canonical model intentionally projects an
   empty map, while direct and replay archives retained different calculated
   master coefficients. The failure was `unsupported_staged_change`, forcing
   a recovery-only live edit for a normal document operation.
2. **P0 — save success is reported as an error.** `save_document` wrote the
   source and returned `nativeSaveSucceeded=true`, `fontSaved=true`, and a new
   source fingerprint, but no save notification was observed. It then returned
   `save_verification_failed`. A subsequent canonical read saw the saved bytes
   and normalized axis/master state, but the MCP persistence projection and
   document listing still reported the document as dirty.
3. **P0 — export review cannot reach its renderer.** `preview_export` returned
   `source_bundle_preflight_failed` with `native_renderer_unavailable` before
   producing any UFO or designspace evidence.
4. **P1 — implicit axis defaults cannot be replayed as null.** Dirty native
   state temporarily materialized `wght=400` and `wdth=100` defaults. A generic
   preview intended to restore the original null representation failed with
   `native field replay failed for GSAxis.default from NoneType: None`. Saving
   later normalized the fields back to null, but the verified mutation surface
   could not express that state.
5. **P1 — master collection order is not exposed canonically.** A master
   `index` projection returned null, and ordinary reads sorted by identity
   rather than the stored master-list order. Exact grid-order proof therefore
   required Python.
6. **P1 — detached and canonical visibility disagree.** The saved canonical
   source correctly reported only Regular visible, matching the baseline, but
   the final detached Python clone reported every master visible. Compatibility
   was unaffected, but a review that trusts the clone for this field would be
   inaccurate.
7. **P1 — the variable-font audit is unnecessarily fragmented.** Establishing
   axes, instances, mappings, origin, master order, coverage, compatibility,
   native interpolation, export readiness, and persistence required many
   separate calls and repeated full-document captures.
8. **P2 — reducer validation is opaque.** A glyph request combining `count`,
   boolean `all`, and boolean `sum` returned only “The request is invalid” with
   no field/type diagnosis.
9. **P2 — execution output limits are missing from the advertised contract.**
   `execute_python(maxOutputChars=30000)` failed at transport validation because
   the real maximum is 8192, but the callable tool description exposed only an
   unconstrained number.
10. **P2 — Knowledge misses the decisive native workflow.** Searching the
   pinned corpus for `GSInstance.addAsMaster` returned no entry even though the
   bundled ObjectWrapper documents the method as equivalent to Glyphs'
   “Instance as Master” command.

The read-only Python audits were also expensive for this modest source: a
bounded no-change audit took about 19 seconds, the complete 28-instance
interpolation audit took about 22 seconds, and the rejected staged edit spent
about 37 seconds before returning the derived-cache mismatch. The final
order-only saved-state audit took about 30 seconds.

## Implementation plan

### P0: make the complete task transactional

1. Classify automatic `instanceInterpolations` as derived when
   `manualInterpolation=false`. Exclude stale cache keys from native archive
   equivalence or deterministically refresh both the direct candidate and
   replay before comparison. Add a regression that inserts four cross masters
   into a five-master, three-axis source and proves native-archive equivalence.
2. Add a typed atomic **instances as masters** workflow. It should accept exact
   static-instance IDs, invoke Glyphs' native interpolation once per instance,
   accept an explicit final master order, and return master/layer coverage,
   compatibility, origin, mapping, and preservation postconditions in one
   immutable preview. It must apply without live-open-world Python.
3. Repair save reconciliation. Observe Glyphs 4 package saves reliably, or use
   a bounded stable-state fallback based on destination fingerprint, native
   dirty state, and canonical equality. A successful native save must update
   the saved baseline and must not leave contradictory dirty projections.
4. Restore the Glyphs UFO/designspace renderer in the installed runtime. If a
   host truly cannot render, report the missing selector/module/resource and a
   concrete recovery action instead of the generic unavailable result.

Acceptance for P0 is one preview, one apply, one source-bundle review, and one
verified save for this scenario, with no open-world fallback and no residual
dirty state.

### P1: make review exact and fast

1. Expose stable collection `index` for axes, masters, and instances, and allow
   natural collection order in `read_document`.
2. Define null/default replay semantics for optional GSAxis fields so omitted
   source values round-trip without relying on a later save normalization.
3. Preserve or explicitly reconcile master visibility in detached GSFont
   clones so read-only Python and canonical source projections cannot disagree.
4. Add one bounded variable-font source review that reports axes and defaults,
   internal/external mappings, origin, ordered master locations, instance
   locations, special layers, glyph/master coverage, native compatibility,
   static interpolation results, and export-preview readiness.
5. Cache one stable canonical snapshot across related read-only review calls so
   large glyph sources are not cloned and compared repeatedly.

### P2: improve diagnostics and guidance

1. Return field-aware reducer errors and either support boolean counting or
   recommend the correct predicate/reducer form.
2. Publish the `1..8192` output/error limits in the MCP tool schema.
3. Add Knowledge entries for `GSInstance.addAsMaster`,
   `GSInstance.interpolatedFont`, and the automatic-versus-manual
   `instanceInterpolations` contract.
4. Add this scenario to the live release gate with explicit assertions for
   grid order, origin, mappings, 29-instance preservation, 422-glyph coverage,
   28 successful static interpolations, zero incompatibilities, renderer
   readiness, verified save, and clean persistence state.
