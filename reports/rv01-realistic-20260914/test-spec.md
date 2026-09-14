# RV01 — realistic current-v2 evaluation

Baseline: running private lean v2 Beta 1, sidecar 82daa62ac227 / bridge 8b74a8d27ae4; Glyphs 4.1 (4107). Latest grouping candidate installed before trials. Pinned open-source Roboto Slab: 1,272 glyphs, three masters. Original files and existing GUI fonts are protected; only independently opened/disposable copies are edited.

## Tasks and predeclared checks

| ID | Realistic brief | Route and expected result |
|---|---|---|
| T01 | Inspect `o`, `a`, `aacute`, `space` in the three weight masters, including fractional widths | Public MCP; exact native IDs, widths and bounds; bounded active node evidence |
| T02 | Increase `o` advance by 12.375 units, review, apply, discard | Public width job; exact requested widths; all shapes, anchors and unrelated glyphs unchanged; exact discard |
| T03 | Repair deliberately displaced `o` contour starts across three weights | Public start_nodes; explicit path/master correspondence; geometry unchanged; report ambiguity honestly; discard |
| T04 | Adjust one `o` handle by +2.5 x in three masters | Authored native script; exactly one identified off-curve per layer moves; retain all existing objects and other data |
| T05 | Insert a midpoint into a straight `H` stem edge in every master | Authored native script; three added on-curves, exact collinearity, unchanged polygon geometry and widths |
| T06 | Remove a deliberately seeded redundant collinear `H` point | Authored native script; three removed nodes only; recover original polygons; reject non-collinear point removal |
| T07 | Add strategic native extrema to `at` across all masters | Native addNodesAtExtremes; measure actual geometry and topology effects; native compatibility is diagnostic, never a quality guarantee |
| T08 | Place corresponding `o` curve midpoints across all masters | Native-authorized snippet using exact cubic subdivision; compare polynomials before/after at 101 parameters, topology/native compatibility and interpolated correspondence; same parameter is not claimed to improve every interpolation |
| T09 | Create, validate, run and revise a reusable bounded master audit snippet | Installed development helper and native execution; exact counts/types/widths; no edits, fresh results, no repository/v1 dependency in delivered snippet |
| T10 | Review real OpenType code and classify active/disabled features and class references | Configured feature skill first; preserve unavailable-tool finding; separately labelled native script control with source-file cross-check |
| T11 | Add opt-in `ss20` mapping `g` to existing `g.ss01`, compile and shape | Native GSFeature script; preserve prior features/classes/prefixes and glyphs; actual compiled GSUB shaping proof required, no inference from compile return alone |
| T12 | Diagnose an invalid feature referencing a missing glyph and demonstrate corrected result | Negative control on disposable source; explicit compiler error, then corrected code compiles/shapes; no modification of unrelated feature code |

## Accuracy and measurement

All task edits receive fresh independently loaded copies; public tools receive IDs only from public discovery. Test setup and independent read-only verification are labelled separately from primary actions. No bridge/tool/skill changes, v1 runs, implicit original saves or custom Undo machinery.

Unchanged coordinates, widths, metadata, transforms and object identities require exact equality. For an explicitly split cubic, polynomial error tolerance is 1e-9 font units; for native extrema use a separately computed adaptive polyline Hausdorff bound of 0.05 font units and report the observed approximation, not an exact-outline claim. Curve edits have intentional geometric change and are judged visually with an overlay. Native compatibility must be checked across all three masters whenever topology changes. A topology edit must cover every intended master; a subset alone is not a whole-glyph compatibility repair.

This is one exploratory complete agent attempt per task, including its corrections. Native operation repeats are measurement controls only, not additional complete coding sessions. Report sample counts, wall time, native action time and HTTP time separately. There is no matched v1 or speed-comparison claim. Token estimates use tiktoken/o200k_base over recorded literal payloads/artifact/skill excerpts; billed usage unavailable.

LLM judgment uses a 1–5 anchored rubric for correctness evidence, design usefulness, skill accuracy, workflow effort and delivery. 1=blocked/misleading, 2=substantial intervention, 3=workable with friction, 4=minor friction, 5=smooth and verifiable. Unsupported and unverified remain explicit. Preserve first-attempt errors. The LLM judge must cite actual evidence and must not upgrade a deterministic failure to a pass.

## Execution-method clarification

The 0.05-unit extrema tolerance was retained. Uniform polyline sampling was used for visual diagnostics, then strengthened by a numerical control-polygon deviation bound with full original-segment parameter coverage; it was not reported as a certified adaptive-polyline Hausdorff result. The LLM evaluation is by the executing agent, not an independent/blinded rater. Per-task end-to-end times and full-session repetitions were unavailable and are not claimed. The original wording is retained in test-spec-before-report-clarification.md.
