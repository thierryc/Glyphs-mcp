# Explicit polygon reconstruction

Use this mode only when the user requests converting a polygon or excessive
straight-line nodes into curves. A request to inspect, remove duplicates or
tidy a path does not imply reconstruction. Changing smooth/corner flags alone
does not create curve segments or their handles.

Require `path.fit-curves.v1`, `outline.fit-polygon.v1` and native preparation on
the bound connection. A missing capability is an installation/qualification gap;
do not copy the fitting algorithm into a script. No additional top-level MCP
tool or skill is introduced.

Example options for `start_edit_workflow(kind="path_fitting", ...)`:

```json
{"targets":[{"glyph":"infinity","paths":[
  {"path":0,"keepNodes":[16,32],"cornerNodes":[]}
]}],"layers":"all_interpolation_layers","maxDeviation":0.5,"cornerAngle":45}
```

Use `mode="preview"` for an explicit preview and `mode="apply"` for authorized
reconstruction. Retain the same workflow/key for polling and retries. Typed
saved-baseline prerequisites, guarded apply, selective Undo and separately
authorized Save remain unchanged. Use the existing workflow card for substantial
results and native Changes Against Reference for visual review; leave edits
unsaved. Keep/Save/Undo retain their existing meanings.

Targets are 1–100 exact glyphs, each with 1–100 exact path indices. There is no
`all` selector. `keepNodes` preserves source coordinates; `cornerNodes` also
preserves a corner connection. Both use zero-based indices from fresh geometry
reads and are applied to corresponding contours in every interpolation layer.
Node 0 always survives. Geometric turns at least `cornerAngle` degrees are
protected in every corresponding layer; the default is 45 degrees. Do not raise
that threshold without reviewing whether the user intends to soften those
corners. Fitting may change connection flags at other retained nodes.

The initial implementation accepts closed, filled LINE polygons with 4–512
nodes. Existing curves use coordinated cleanup. Open strokes, Pen profiles,
locks, native hint references, node names/metadata and path user data are held.
It never removes overlaps, changes fill, reverses contours or rotates starts.
Missing paths, incompatible families and incomplete special-layer branches are
visible refusals, never silently reduced targets.

`maxDeviation` defaults to 0.5 font units and must be in `(0,10]`.
`cornerAngle` must be in `(0,180]`. A budget is not an achieved error. Native
grid effects may prevent a useful fit at the default tolerance. Report that
reason and let the user choose a different budget; never increase it on retry.

Corresponding spans use common retained source nodes and split locations. Each
layer must reduce total stored points, including handles. Straight spans remain
lines when they qualify in every layer. Proposals report before/after counts,
continuous source-span bounds, cumulative boundary bounds, native interpolation
samples and held families. Samples include authored locations, export instances,
pairwise midpoints and both sides of bracket boundaries; they are not a
continuous designspace guarantee. No G2 or export-equivalence claim is made.

Optional harmony is a separate Curve Inspector operation. If composing changes,
retain the original reference and qualify the combined result against its budget;
separate passing step budgets do not prove cumulative preservation.
