# Lean kerning collision workflow

For conversation edits, use the [shared edit workflow](../../glyphs/references/edit-workflow.md)
with these same request fields when `edit.workflow.v1` is advertised. The
low-level job examples below describe operation scope and existing guards.

Use this workflow when `get_status` advertises the twelve-tool lean catalog.
For inspection alone, use the [stored kerning read reference](../../glyphs/references/kerning-reads.md);
dirty and unsaved fonts are readable without a job or Save. Reuse the intended
document ID. Stop after reporting when no repair was requested.

For explicitly requested collision-job preparation, use a clean saved source
(disposable copies for tests). Inspect source and dirty state before preparing;
do not silently save a dirty font to satisfy the job prerequisite.

Choose explicit glyph-name pairs and exact native master IDs already identified
on this connection. For example (replace the IDs with that font's actual IDs):

```json
{"document_id":"KNOWN_DOCUMENT_ID","kind":"kerning_collision","options":{"pairs":[["A","V"],["T","o"]],"masters":["LIGHT_ID","REGULAR_ID","BOLD_ID"],"direction":"LTR","targetGap":5.125,"denseStep":10}}
```

Call `start_job` with that request. Omit `delta` and `glyphs`.

| Option | Contract |
|---|---|
| `pairs` | Required, 1–3,000 unique ordered glyph-name pairs. No automatic class expansion. |
| `masters` | Up to 100 unique exact IDs. Omitted/empty means all saved masters; prefer explicit scope. |
| `direction` | `LTR` only (default). Stored reads separately support RTL/vertical. |
| `targetGap` | Font units, default 5; finite 0–1,000. A clearance target, not a kerning delta. |
| `denseStep` | Font units between refinement heights, default 10; finite 0.1–100. |

Computation stays outside Glyphs and uses native intersections and native
effective-kerning resolution. Five coarse heights refine near the threshold;
the report preserves the coarse minimum and the refined minimum and density.

Use a bounded polling loop: wait about 500 ms between preparation checks and
100 ms between short apply/discard checks; stop on a terminal status or a
reasonable timeout. Cancellation uses `discard_job` immediately, without waiting
for the next preparation poll. Reconcile the same job ID after uncertain replies.
Require `include_preview` in this connection's `get_job`, `apply_job` and
`discard_job` schemas; if absent, update the private bridge, sidecar and skills
together. Set it to `false` for those calls to avoid repeated samples. Counts,
errors, activity and report metadata remain; `previewIncluded:false` explicitly
marks omission. Defaults still include previews.

When ready, read the complete local JSON at `report.path` **once**, including
unavailable pairs, and review it before applying. A response sample is not the
complete report. Retain that evidence in context. Corrections create exact
pair exceptions, leaving shared class values and unmeasured peers unchanged.
Only a positive fractional loosening needed for the target gap is proposed.
This does not promise clearance between samples or optimal optical kerning.

Choose density for the feature: the P10 test's spike at y=52.625 was missed at
`denseStep:10` and detected at `0.125`. A 100-unit shared height permits that
finer step; a 1,000-unit span exceeds the 4,096-height guard and is unavailable
at that density. No automatic denser retry or exhaustive-clearance claim.

After reviewing the result, `apply_job` displays the reversible native change.
Read back exact stored values with the retained document ID and proof the chosen
strings. Native Undo/Redo uses the left glyph's Edit-view history (all touched
masters of that glyph); use `discard_job` for the whole job's still-current
targets. It restores the exact prior presence and value. A disabled menu or
conflicting target is not successful restoration; report it. Do not infer clean
document indicators from restored values. Use `accept_job` only when the user's
task authorizes persistence of the reviewed whole document; do not save an
applied design merely to complete the workflow.

A failed job naming missing saved-source glyphs or masters prepared no applicable
edit. Keep the document ID and correct the pair names/master IDs; do not
rediscover documents or substitute targets. Dirty/stale-source errors are
different: resolve that source state before preparing again, with no implicit Save.
