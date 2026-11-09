# Quality review and existing routes

Use the existing read-only `path_diagnostics` job first. Findings identify exact
paths/nodes, stable report-scoped IDs, state hashes, confidence and evidence.
Quality candidates have no automatic repair payload. Re-read after edits.

| Finding or intent | Route |
|---|---|
| Dense LINE polygon | Explicit `path_fitting`; ordinary cleanup preserves corners. |
| Zero handle | Review hidden/coincident segment handles separately from node visibility or duplicate LINE removal. Extraction is not implemented by polygon fitting. |
| Handle extending past its forward tangent intersection | `handle_triangle_violation`; review possible loops/cusps. Parallel or intentional inflecting configurations are not automatically invalid. |
| Interior extrema | Review `add_extremes` with `force=false`, shallow curves and interpolation correspondence. Do not add all extrema indiscriminately. |
| Inflections or stationary curve points | Review design intent; use the existing De-kink workflow for HOI interpolation kinks. An inflection is not itself an error. |
| Winding/nesting mismatch | Existing `correct_path_direction`, or explicit reversal if only direction is authorized. Native correction also changes contour order and starts. |
| Tiny or distant contours | Review intentional details, marks and wide/tall designs before any deletion. Thresholds are candidate signals, not defects. |
| Intersections, tangencies or overlaps | Inspect native appearance. Keep intentional source overlaps; use detached `remove_overlap` inspection under separate authorization to find resulting debris. |
| G2 harmony or balancing | Use the installed Curve Inspector shared engine and its companion skill; do not reimplement formulas in this skill. |

Direction review assumes simple, separated closed filled contours and reports
alternating winding with nesting depth. Overlaps/ambiguous clearance hold that
classification. For correction across masters, resolve exact ordinary,
intermediate and alternate layer IDs and use explicit native-action targets;
the API's `all_masters` selector is narrower than Glyphs' all-masters menu command.
Recheck direction, starts, shape order and correspondence afterward. For
matching starts or shape order, reuse the existing compatibility workflow.

Quality analysis currently covers stored line/cubic foreground geometry, without
expanded components or strokes. Local quality checks cap each path at 512 stored
points; the nesting audit caps the eligible paths in each layer at 512 points.
Quadratics or exceeded limits produce explicit held coverage and make the report
incomplete. Structural diagnostics retain their existing 4,096-node path limit.
Native star/raindrop effective geometry belongs to Curve Inspector's engine.

The native winding review uses clearance certification and a flattened nesting
test. It is advisory, not a repair oracle. Handle balance compares relative
lengths to a forward tangent intersection; intentional asymmetry is valid.
Cross-master distribution and opposing inner/outer curvature remain visual or
companion review tasks, not automatic Path Doctor fixes.

Reference: [Drawing good paths](https://glyphsapp.com/learn/drawing-good-paths),
[path direction](https://handbook.glyphsapp.com/editing-paths/#controlling-path-direction),
and [Curve Inspector's shared workflow](https://github.com/thierryc/Glyphs-mcp/tree/main/src/companions/curve-inspector).
