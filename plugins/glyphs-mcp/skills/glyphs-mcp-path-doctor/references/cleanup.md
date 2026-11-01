# Coordinated path cleanup

Require `path.cleanup.v1` and native preparation on the bound connection. Use
`start_edit_workflow(kind="path_cleanup", mode="apply", options=...)` for an
explicit cleanup request. Inspection alone uses `path_diagnostics`; an explicit
preview uses `mode="preview"`. Never emulate a missing advertised capability.

Options use explicit glyph names or `glyphs:"all"`,
`layers:"all_interpolation_layers"`, `policy:"exact"|"bounded"`, and independent
`operations`: `duplicates`, `seams`, `collinear`, `near_nodes`, `align_handles`,
`simplify_curves`. Default operations are `duplicates`; seam normalization is
separate. Bounded operations require bounded policy. `maxDeviation` defaults to
0.5 font units; `angleTolerance` defaults to 2 degrees of maximum handle rotation.
Both must be positive and at most 10. These are budgets, never achieved errors.

The engine prepares detached copies, coordinates ordinary/brace layers and
complete explicit bracket branches, and holds ambiguous or incomplete branches.
It never invents missing branch layers or repairs existing incompatibility.
Every corresponding layer must qualify. Consecutive duplicate LINE endpoints
retain the earlier node. Profile-bearing duplicates need separate qualification;
closing seams retain their existing profile-aware normalization rules.
Exact proposals also compare real segments and endpoint profiles at native
sample locations. Component-dependent interpolation and incomplete bracket
branches are held when that validation cannot be established.

Bounded changes initially support closed filled line/cubic outlines, without
Pen profiles, hints, locks or authored node references. Corners and contour start
nodes are protected. Native node removal proposes geometry; measured cumulative
bounds and native intermediate checks qualify it. Report tested native locations
explicitly; sampled interpolation does not prove a continuous designspace bound.
Preserve the separate Pen-point cleanup strategy and De-kink workflow.
Samples cover affected authored locations, active export-instance locations,
pairwise authored midpoints and both sides of bracket boundaries. The engine
retains font interpolation settings on isolated copies. Conservative Bézier
control-hull separation holds unresolved intersections and tangencies.

## Card and native comparison

Use one existing workflow card for requested controls or substantial results.
The card offers Analyze and Apply cleanup, independent operation controls,
exact/bounded policy and numeric inputs alongside sliders. Changing settings
invalidates the old proposal. `respond_edit_workflow` accepts `cleanup_settings`
and `cleanup_apply` only through its revision-bound `configure_cleanup` action.
Scope remains fixed; internal document IDs and tokens never become user inputs.
Analyze is read-only and works on dirty/pathless fonts. Application retains the
existing typed Save/Save As prerequisites and warning/recovery lifecycle.

After application leave edits unsaved for review. Use **View → Changes Against
Reference** and **Edit → Comparison Reference → Last Saved**. Saving advances
that reference. Exact duplicate removal may produce no visible ink change;
report removed-node counts and preservation checks. Do not build a separate
outline viewer or treat the reference overlay as geometric proof.

Offer existing Keep without saving, Save and selective Undo actions. Set
`auto_keep=false` for an explicitly requested comparison review. Verify actual
results, summarize held glyphs and reasons, and rerun diagnosis. Do not promise
that every finding is an error or that every path can be repaired automatically.
