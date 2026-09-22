# Glyphs MCP Sidecar

This process owns MCP, saved-source copies, hashes, temporary jobs, and
`glyphs-cli`. It connects to the loopback-only Glyphs bridge on port 9681.

Conversation edits use `start_edit_workflow`, `get_edit_workflow` and
`respond_edit_workflow` (`edit.workflow.v1`). One standard, self-contained MCP App
is available through `ui://glyphs-mcp/edit-workflow-v1.html`; all actions also
work through text. The coordinator owns request retention, idempotency and
revisions, while existing job/save services retain native validation and recovery.
Complete authorized edits apply automatically; previews and report warnings
wait for review. A prerequisite Save and continue saves existing work once;
the resulting edit remains unsaved until separately authorized.

The original nine tools keep their signatures. Low-level jobs change nothing
until `apply_job`; application is reversible and never saves. `accept_job`
verifies and saves the whole font. Undo/Redo and guarded discard remain native.

`start_job(kind="spacing", options={...})` adds external spacing suggestions
without another tool. Options are `reference` (default `auto`; `*` means self),
per-glyph `references`, `masters`, `widthMode` (`auto`, `preserve`, or
`proportional`), `area` (400), `depth` (15 percent of x-height), and `sampleStep`
(5 units). Omit `delta` for this job. `glyphs` limits the glyph names; omitted
names select all master layers. Special layers are outside this first workflow.

The workflow selects H for uppercase, x/n/o for lowercase, and one/zero for
decimal figures, with recorded fallbacks. Explicit references never silently
fall back. Native intersections supply the sampled evidence; computation runs
on detached native copies with glyph context for components. The worker's private,
never-saved font uses a zero display grid so native bounds retain fractions; the
editor's grid remains unchanged. Translation verification compares output
coordinates, since native curve extrema can be approximate. Output consists only
of existing width and translation patches, with fractional values retained.
It preserves each tabular width, zero-width marks, metric keys, and native
component alignment. It does not infer tabularity from a family name. Figure
widths within 0.005 em, explicit preservation, tabular suffixes, and fixed-pitch
metadata supply the preservation evidence. `proportional` disables automatic
equal-figure detection; named tabular glyphs and fixed-pitch widths remain kept.

`get_job` includes a bounded report sample and the path of the full external
`report.json`, with selected references, fallbacks, metric preservation reasons,
and unavailable targets. The report separates measured suggestions from skipped
targets. These are reference-selection and metric-preservation improvements,
not a claim of universally optimal optical spacing. The initial area workflow
does not add a balanced italic-spacing engine or custom outline corrections.

`start_job(kind="kerning_collision", options={"pairs": [["A", "V"]]})`
measures explicit LTR glyph pairs outside the editor. Options are `masters`
(all by default), `targetGap` (5 units), and `denseStep` (10 units). Native
`nextKerningForLayer:direction:` resolves groups and exceptions. The five-height
coarse scan refines when its minimum is within `max(10, denseStep)` of the target.
Refinement retains the coarse observations and adds a bounded dense scan.

Corrections only loosen a measured pair to the requested sampled clearance.
They create or update exact pair exceptions; shared group values remain intact.
The explicit kerning patch carries master, direction, keys, and nullable numeric
before/after values: `null` means absent, while zero is a stored value. Native
set/remove methods apply the patch and discard restores the original presence
and fractional value. `read_entities` supports exact `kind="kerning"` selectors
with `master`, `direction`, `left`, `right` and `fields=["value"]`.
The bridge also distinguishes RTL and vertical storage; collision geometry is
currently LTR only and rejects other directions. Reports include native effective
values, stored exceptions, class keys, scan density, minima, and unavailable pairs.
This detects sampled collisions; it does not guarantee clearance between samples
or produce optimal optical kerning.

`start_job(kind="start_nodes", glyphs=["o"], options={...})` matches one explicit
contour across 2-32 masters. Options are `path` (index 0), `masters` (all),
`referenceMaster` (first selected master in font order) and `referenceNode`
(the reference's native start node by default). The reference node is a matching
landmark; the reference layer's existing phase stays unchanged. Other layers
receive only native cyclic reorders, so repeating the job is a no-op.

Landmark matching retains the tested position/extrema, tangent, node-type and
curvature-class checks. Ambiguity, incompatible topology, open contours and
missing targets reject the job before any editor write. The explicit patch
contains the layer, contour index, node count, cyclic shift and before/after
outline hashes. Native `GSPath.makeNodeFirst:` preserves the node objects,
metadata, hints and contour geometry; it stores the native start at the end of
the node array. This supplies supported correspondence, not arbitrary master repair.

For workspace testing, add `src/protocol` and `src/sidecar` to `PYTHONPATH`.
The release builder copies both packages into one portable sidecar tree.

`start_job(kind="slant", glyphs=[...], options={...})` runs native slant externally.
Options are `angle` (12°, nonzero, ±30°), `pivotY` (0), `masters` (all), and
`preserveStraightStems` (false). The optional pass conservatively restores the
perpendicular width of accepted opposite straight sides. It skips curve-adjacent
segments and unsafe corrections. Native slant/Cursivy/thickness-only comparison
and independent output-coordinate measurement are recorded in
`build/slant-native-benefit.json`; the benefit claim is limited to this objective.

The explicit coordinate patch carries bounded node/anchor/component selectors,
before/after vectors and a topology guard. Native setters retain node objects,
hints and fractions. Advance widths remain unchanged; anchors follow native
slant. Manual components use conjugation when their base is also selected to
avoid double shear. Lossy native component matrix round trips reject preparation.
Automatic component layers are skipped without changing their local data;
their displayed outlines can inherit changed bases. Special layers, arbitrary
smart-component correction and a full balanced-italic construction are outside
this workflow. Reports include correction evidence and skipped layer reasons.

For local evaluation, build with `scripts/build_simple_v2.py` and run
`scripts/install_simple_v2.py --python <venv-python> --glyphs-app <Glyphs-4.app>
--companion curve-inspector --companion reference-inspector --start`.
The installer backs up replacements and starts the external sidecar with a user
LaunchAgent. It uses the supplied Python environment, which must contain FastMCP.
The existing Codex connector uses `http://127.0.0.1:9680/mcp/`. HTTP requests are
stateless so clients keep working after a sidecar restart. Job IDs belong to the
service; restarting the sidecar ends its in-memory job session. Restart Glyphs
to load changed native bundles. The sidecar can also run with stdio and no LaunchAgent.

`dimensions_edit` prepares up to 100 per-master reference-note changes. Blank fills
need no confirmation; overwrites/clears require exact `approved_overwrites`
entries after conversational approval. It retains the saved-clean-source workflow
and never saves on apply. See the Dimensions skill reference for the full policy.
