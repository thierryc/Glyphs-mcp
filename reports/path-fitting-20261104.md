# Path Doctor polygon fitting — candidate qualification

The source candidate was tested with the existing plugin-free `glyphs run`
harness against `/Applications/Glyphs 4.app`, version 4.2, build 4202. No live
font was supplied to the CLI. Fixtures create detached native fonts only.
No runtime was installed, linked, restarted or reloaded. The loaded MCP route
and workflow card have not been verified against these candidate bytes.

Reproduce with `scripts/qualify_path_fitting.py`, using the configured app's
Python arguments from `glyphs_mcp_protocol.python_runtime.python_arguments`.
The existing `qualify_path_doctor.candidate` loader isolates source modules;
it does not replace imported running bridge modules. Full local synthetic
results are under `/private/tmp/glyphs-path-fitting-native-20261104-verified` and are
not release assets.

## Native checks

- Ordinary two-master family: detached preparation, point reduction, native
  interpolation samples, guarded apply, retained native path/start identities,
  exact after-hash and exact snapshot restoration passed.
- Intermediate/brace family: corresponding topology and authored/native sample
  validation passed on all three stored layers.
- Complete bracket branches: four stored layers, both sides of the branch
  boundary and native interpolation checks passed.
- Outer contour plus two counters: nesting, winding, combined outline budget,
  coordinated application and restoration passed.
- Native `NSUndoManager`: exact Undo and Redo passed through the existing
  bridge snapshot writer for both ordinary master layers.
- Grid/tolerance refusal: a fractional polygon fixture was held at the default
  0.5-unit budget because its native interpolated outline exceeded that bound.
  Separate positive fixtures explicitly requested a 2-unit budget; the engine
  never changed a request's tolerance.

The two native positive master layers each reduced a 64-point polygon to fewer
stored points, including handles. Pure regression fixtures separately exercise
a polygonal infinity-like outline with two counters, intentional corners,
corresponding split schedules, stale state, unsupported targets and insufficient
tolerances. Quality tests use analytic cubic/area fixtures and nested contours.

Focused source regression verification passed 243 tests across fitting, quality,
cleanup, outline editing, bridge/protocol/sidecar, workflow/card behavior and
source inventory documentation. Three existing Swift/localhost checks passed
when rerun outside the sandbox that blocked their compiler cache/socket access.
The full suite had first passed 3,413 tests; stale inventory guidance was
corrected and its failed checks rerun. A task-expiry timestamp check passed on
rerun. No claim is made that the full suite was rerun after those targeted fixes.
Skill synchronization and the lean package check also passed.

## Capability and limits

Advertise `path.fit-curves.v1` and `outline.fit-polygon.v1` only on the qualified
4.2/4202 host with the required native attribute selectors. Source and prepared
patch guards remain authoritative at apply. Direct `outline_edit` intake cannot
select `fit_polygon`; it is prepared by coordinated `path_fitting` jobs.

Initial scope is closed filled LINE polygons, 4–512 nodes, without locks, hints,
Pen/stroke profiles, names or authored metadata references. Special branches
must satisfy the existing complete-family grouping rules. Corresponding layers
share segmentation. Every layer must reduce total stored points and pass its
original cumulative budget. Native interpolation evidence is sampled; no
continuous designspace, G2, export, persistence or rasterization guarantee is made.
Save/reopen precision, full GUI workflow delivery and additional host builds
remain separate checks. G2 and HOI repair keep their existing companion routes.
Measurement sampling is capped at 65,536 points and topology subdivision at
8,192 cells per contour; exceeded work budgets hold the proposal instead of
allocating unbounded geometry. Short polygon edges cannot be retained at
otherwise smooth joins just to satisfy point reduction.
