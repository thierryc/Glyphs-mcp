# V1 → lean v2 feature and intent audit

**The smaller interface is intentional, but the feature gap is not yet fully
accounted for.** There are confirmed setup/documentation inconsistencies, seven
capability groups requiring a feature-level decision, and a separate
master-compatibility implementation that has not reached the desktop candidate.
This review does not recommend restoring the v1 catalog wholesale.

## Baseline and method

Reviewed the current working source at `build/milestone7/desktop`, based on
`1273347c`, including its uncommitted desktop documentation. One public
`get_status` confirmed the running private Beta 1/build 43 on Glyphs 4.1 (4107):
seven tools, five job kinds, sidecar `82daa62ac227` and bridge `8b74a8d27ae4`.
[Observed identity/capability projection](runtime-observed.json).

V1 is the pinned 1.11.0 catalog: **87 active tools, 76 model-visible and 11
app-only**. All names match Report 01's historical catalog. Its recorded runtime
was `1.11.0+c98c9840e87a` on Glyphs 3.5; this audit did not restart or retest v1.
[Historical identity](v1-historical-identity.json).

The audit maps all 87 tools to **39 user-facing capability groups**, with no
unmapped or duplicate entries. See the [complete feature matrix](feature-matrix.md),
[per-tool CSV](tool-map.csv), [structured assessments](features.json) and
[source hashes/setup evidence](facts.json). Existing benchmark failures remain
historical findings; a registered v1 tool does not imply it worked correctly.

“Documented” means a deliberate route or scope restriction exists. “Decision
needed” means the absence is verified but no feature-specific deferral or adequate
equivalence justification was found in the reviewed material. It is not proof
of an accidental deletion. “Documented with workflow gap” means the native-only
boundary is stated, but an equivalent task recipe or qualification is incomplete.
The seven-tool limit does not prevent bounded additions to `read_entities`.

## Findings requiring action or a decision

| Priority | Gap | Observed difference and intent assessment | Recommended disposition |
|---|---|---|---|
| High | Stale installed skills | Seven specialized installed skills still require `get_server_info` and `apiMajor == 2`; all claim the v2 surface, six explicitly allow implicit invocation. They are outside the current eleven-skill manifest. This is a real setup inconsistency, not a justified feature substitute. | Retire incompatible entries through ownership/backups or clearly preserve/report protected conflicts. Do not migrate every family or edit plugin caches merely to remove the mismatch. |
| High | Font View and current context | V1 returned selected glyphs, selected master and font context. V2 reads only `currentTab.activeLayer`; no Font View multi-selection or explicit frontmost-document marker. The single-layer node-detail limit was deliberate; it does not establish an intentional loss of compact selection context. | Decide a compact native context/selected-glyph projection in existing reads. This is the strongest day-to-day gap. Never widen a selected-glyph request to the full font. |
| High | Glyph and layer discovery | V1 enumerated glyphs and a glyph's layers. V2 needs known glyph names and exact layer IDs; master IDs are enumerable, but special/backup layers cannot be discovered through an equivalent layer list. Full paths and component data are also absent. | Prioritize bounded glyph/layer discovery; separately decide bounded one-layer structural details. No full-font geometry dump. |
| High | Kerning discovery | Exact pair reads are retained and gain RTL/vertical storage support. V1 could list the stored table and glyph kerning groups. V2 requires known names/group keys; the skills explicitly prohibit guessing. | Decide bounded group membership and pair discovery. A collision-preparation report can expose keys but requires a saved clean font and should not be the inspection route. |
| Medium | Master properties | V1 exposed axes-related weight/width values, italic angle and vertical design metrics. V2 exposes ID/name only. P04 was master identification, not a full-property parity test. | Add selected native scalar fields or explicitly defer them. These need no editing job or new MCP tool. |
| Medium | Instances | V1 had instance metadata inspection. V2 has no instance selector. Native scripts can inspect instances, but the same read workflow is not packaged. | Decide bounded instance reads versus a documented native-only Beta 1 route. |
| Medium | Numerical curve reports | V1 exposed adaptive events, continuity and cross-master quality comparisons. V2's companion draws a curvature comb; that is not the same analytical evidence. | Explicitly defer the reports or specify an external bounded diagnostic recipe. Keep the visual companion. |
| Separate accepted work | Master compatibility | The earlier inspect/normalize/reorder plan is absent from current jobs and read capabilities. An implementation, fixture and isolated-test record exist in the **outer worktree**, but installed-editor qualification was pending. | Choose integration plus fresh qualification, or record an explicit Beta 1 deferral. Do not blindly copy older bridge/Undo code over current improvements. |

The seven “decision-needed” groups in the matrix are glyph metadata/inventory,
master properties, instances, layer/geometry inspection, current selection,
kerning discovery and analytical curve reports. The table combines related
discovery items for readability. These are product decisions, not seven proven
runtime defects.

The master-compatibility work is **preserved, not lost**. Its original
[implementation record](separate-compatibility-record.md) states that isolated
native checks and 306 relevant regressions passed, but editor qualification did
not finish. [Source/evidence locations and hashes](separate-compatibility-work.json)
identify that separate candidate. Those results do not qualify integration into
today's desktop source. This is also not a missing dedicated v1
`master_compatibility` tool: v1 had path/shape evidence, start-node alignment and
general scripting. Its “compatibility” path metadata included host shape-format
warnings, not a complete native master-compatibility service.

## Intentional differences, with limits stated explicitly

| Capability | Current v2 outcome | Omitted by mistake? |
|---|---|---|
| Arbitrary live Python MCP calls | Native script files, CLI or authorized in-app execution, with focused skills and offline KDB. | **No.** Explicit architecture decision. A saved-source CLI run does not see unsaved live edits or inherit MCP discard guarantees. |
| General point/path edits; glyph create/copy/delete/properties | Native coding/UI. RV02 tested several real outline tasks. | **No at the tool level.** Every former operation is not automatically qualified by those examples. |
| Add anchors, components and corner hints | Native coding/UI; no corresponding edit job. | **Deliberate tool reduction; task coverage incomplete.** Populated-hint preservation remains unverified in RV02. |
| Absolute width/sidebearing setters for a chosen master | Additive all-layer `width_delta` and sampled spacing jobs; exact setters require native work. | **Documented limitation, with a workflow gap.** A delta across backups/special layers is not an acceptable substitute for a single-master request. |
| Arbitrary kerning set/remove | Native editing; collision jobs only propose measured loosening. | **Documented native-only boundary.** Still worth a short precise recipe for normal kerning work. |
| Spacing engine/options | Retained reference/area workflow and guards needed by current jobs; reduced rule/default/debug interface. No managed spacing-guide tool. | **No.** Source explicitly says it ports a subset. Persistent v1 settings are not equivalent to v2 job options. |
| Automatic collision-pair discovery/proof tabs | Explicit-pair collision jobs; native proof tabs. | **No for explicit-pair scope.** Document the lost convenience; no universal collision-scan claim. |
| Full optical italic and compensated scaling | Mechanical slant, optional accepted straight-stem correction; no full balanced engine, arbitrary master copying or compensated-scaling candidate. | **No.** Explicitly excluded in the lean benefit queue. Slant does not set master `italicAngle`. |
| Tunni and custom smoothness repair | Not ported as algorithms/jobs; native/manual work remains separate. | **No.** Explicit exclusions. Native tools must not be claimed mathematically equivalent without evidence. |
| Curvature overlay | Independent Curve Inspector, controlled through native UI. | **No.** Function retained with different access; no public overlay-control MCP tool. |
| Candidate/history framework and global change overview | Per-job reports and native Undo/Redo/discard; Reference Inspector compares saved/file/Git references. | **No.** No replacement history or proposal-session framework is intended. |
| Embedded MCP feedback panels and clickable review targets | Agent reports and native UI replace parts of the experience. | **Intentional architecture change; incomplete convenience parity.** Per-glyph/style-set deep links and embedded plans are absent. |
| Save and dirty/pathless mutations | Native Save is acceptance. Reads support dirty fonts; jobs require a clean saved source. | **No.** Deliberate source-safety boundary. V1's ability to mutate dirty/pathless fonts is not retained by these jobs. |
| OpenType inspection/editing | Current native feature skill, compile diagnostics and qualified export/shaping loop. | **Earlier setup gap repaired in RV02.** One-call style-set substitutions/group links still lack an equivalent focused convenience recipe. |
| Unicode/PUA allocation and icon-font policy | No lean allocator or managed icon-font skill. | **Assignment-tool omission is documented.** Prior-map/range/collision safeguards are not recreated by generic native scripting; explicitly defer or port focused guidance. |
| LitSquare metadata/roles and Metadata Inspector | Removed from the lean bridge. | **No.** The reset explicitly removed them; native stored data is not intentionally erased. |
| IconGrid integration | Existing standalone Icon Grid remains independent; MCP center read/set/reset absent. | **No.** Explicit non-duplication decision. Independence does not preserve the removed agent controls. |
| Annotations and managed annotation groups | Native UI/scripts; no corresponding public read/write/group policy. | **Native-only boundary is deliberate; specialized recipe/qualification absent.** |
| Master stems, custom parameters | Native Font Info/scripts, not direct reads/setters in the lean contract. | **Native-only boundary documented; focused coverage incomplete.** |
| Designspace/UFO export and generated build scripts | Dedicated v1 exporter absent. Native TTF export was tested in RV02. | **MCP export omission intentional.** TTF export is not Designspace/UFO parity; defer the exporter explicitly or qualify an existing external route. |
| Documentation retrieval and plugin scaffolding | Offline bounded search/get, six plugin templates and script workflow retained for Glyphs 4. | **No omission of the main workflow.** Host target intentionally changes; v1 remains the Glyphs 3.5 route. |

Explicit exclusion evidence: [Simple Reset](../../V2-SIMPLE-RESET.md), especially
native history, independent Icon Grid and Metadata Inspector removal;
[tested benefit queue](../../LEAN-V2-BENEFITS.md), especially excluded Tunni,
compensated scaling, smoothness and balanced italic;
[current public contract](../../content/reference/command-set.mdx).

## Skill inventory and comparison traps

Both manifests have eleven skills, but they are not the same eleven. Eight IDs
are shared. V1's `glyphs-mcp-features` is replaced by the current
`glyphs-mcp-opentype-features`; v1 icon-font and LitSquare skills are absent.
V2 adds master-compatibility/start-node guidance and maintainer-feedback.
Six plugin template types and the local documentation workflow remain available.

The seven incompatible installed skills are icon-font, LitSquare metadata,
color-font, variable-font, production-audit, Unicode semantics and export
validation. Their required gates and checksums are captured in `facts.json`.
Preserving user-modified/unowned skills can be correct installer behavior;
leaving them discoverable as if they were compatible lean-v2 workflows is still
a setup gap to resolve. No ownership or permission to delete them was inferred.

Full color-font, variable-font and production-audit skill families seen in the
older private prototype were **not dedicated skills/tools in the pinned v1
manifest/catalog**. V1's general Python could implement such tasks, and its
Designspace/UFO exporter is counted above. Do not count every prototype feature
as a v1 regression, or call generic Python access a tested complete audit.
Similarly, v1 `get_font_glyphs` already returned primary `unicode`; the missing
multi-codepoint mapping in that one v2 read is not a newly lost v1 field.

Additional documentation errors need correction before release: the migration
guide still says bridge `0.1.0` and “Signed local candidate”; release instructions
still say ten skills, protocol `0.1.0` and a `main` appcast. Current identity,
eleven-skill inventory and the beta-branch launch plan contradict those statements.
These are documentation drift, not deliberate feature differences.

## Recommendation for Beta 1

1. Resolve stale skill setup and migration/version claims through the existing
   ownership and documentation mechanisms.
2. Make a small explicit decision on ordinary context/discovery: Font View
   selection, glyph/layer discovery, kerning groups, then master metrics. If
   included, use bounded native reads inside the existing seven-tool interface.
3. Decide master compatibility separately: qualify selective integration, or
   record deferral and advertise the current skill as start-node correspondence.
4. Explicitly defer the larger specialized engines/audits/exporter where that
   remains the intended Beta 1 scope. Add short native recipes for promised
   everyday tasks such as exact metrics, manual kerning and style-set proofing.

Do not treat this report as authorization to implement every gap. A defensible
Beta 1 can be narrower than v1, but should list each omission and its native,
external, companion or deferred disposition. Current feature-count comparisons
and the matched-task benchmark alone do not establish whole-product parity.

## Verification and preservation

This is a source/catalog/skill review, not another timing or accuracy benchmark.
The collection script checks one-to-one coverage of all 87 active v1 tools and
records hashes for the cited evidence. Eight tools already retired before the
v1 baseline are excluded. No font discovery, native edit, job, installation,
restart or v1 modification was performed. Prior reports remain unchanged.

[Audit verification](verification.json) confirms all 87 definition locations,
the historical catalog match, 118 artifact/source links, seven incompatible
installed gates and 5,180 unchanged files outside this review. These are review
integrity checks, not native feature pass counts.
