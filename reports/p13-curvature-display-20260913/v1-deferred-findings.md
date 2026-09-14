**V1 findings — deferred, no implementation changes authorized here**

User instruction: log v1 failures for later; do not fix v1 now. These observations use v1 `1.11.0+c98c9840e87a`, SHA-256 `c98c9840e87a9bb7773b8fe643f21e86400323874a35c695e8ad01eb5a46bacc`, Glyphs 3.5 (3532). Record 03: 2026-09-10. All targets were disposable fonts; no user font was changed.

| ID | Finding | Status | Evidence |
|---|---|---|---|
| V1-001 | A retained font index can target another document after window activation, as well as after closure. | Reproduced; deferred | [Initial mapping](03-glyph-metadata/v1-adaptive-list/facts.json), [wrong-target follow-up](03-glyph-metadata/v1-dirty-read/facts.json), [correct freshly resolved probe](03-glyph-metadata/v1-edit-probe/calls.jsonl), [earlier closure case](02-document-discovery/recompare-20260910-1508/v1-stale/facts.json) |
| V1-002 | HTTP navigation links use port 9680 while v1 serves on configured port 9682. | Reproduced; deferred | [Public metadata response](03-glyph-metadata/v1-adaptive-read/facts.json), [server configuration before restoration](03-glyph-metadata/v1-before/facts.json) |
| V1-003 | The metadata tool description says “bounded”, but the dedicated list has no glyph selection or limit parameter and returns the complete font. | Contract/capability limitation observed; deferred | [Installed catalog](03-glyph-metadata/v1-timed/catalog.json), [111-glyph response](03-glyph-metadata/v1-adaptive-read/facts.json), [payload estimates](03-glyph-metadata/token-estimates.json) |
| V1-004 | Master-identification request-proxy p95 exceeds the 50 ms target: idle 116.841 ms (n=20), post-edit 73.113 ms (n=16). | Measured threshold misses; cause unverified; deferred | [Report 04 idle facts](04-master-identification/v1-timed/facts.json), [post-edit facts](04-master-identification/v1-edit-probe/facts.json) |
| V1-005 | `get_glyph_paths` converts intentionally unavailable Glyphs 3 bearings to numeric zero. Twelve sampled nonempty-layer bearings are incorrect. | Reproduced; deferred, no fix | [Report 05 dedicated evidence](05-layer-measurements/v1-dedicated-first/facts.json), [native oracle](05-layer-measurements/v1-native.json), [public fallback control](05-layer-measurements/v1-supplemental/calls.jsonl) |
| V1-006 | Layer-read fallback request proxies miss p95 and maximum targets: idle 303.416 / 428.664 ms; post-edit 206.322 / 206.322 ms. | Measured workflow proxy; native cause unverified; deferred | [Report 05 idle](05-layer-measurements/v1-idle/facts.json), [post-edit](05-layer-measurements/v1-edit-probe/facts.json) |
| V1-007 | In Font View with no glyph selected, `get_selected_font_and_master` returns a `NoneType` iteration error instead of font/master context and an empty selection. | Reproduced; deferred, no fix | [Report 06 controls](06-selection-inspection/v1/facts.json), [native Font View evidence](06-selection-inspection/native-acks/v1/022-fontview.json) |
| V1-008 | With a glyph selected in Font View but no Edit View, `get_selected_nodes` returns that glyph/layer as though it were being edited. | Reproduced; deferred, no fix | [Report 06 controls](06-selection-inspection/v1/facts.json), [native no-Edit-View evidence](06-selection-inspection/native-acks/v1/023-fontview-selected.json) |
| V1-009 | `get_font_kerning` accepts a nonexistent master ID and reports a successful empty table, indistinguishable from no stored pairs without separate master verification. | Reproduced; deferred, no fix | [Report 07 invalid-master control](07-stored-kerning/v1/facts.json), [timestamped public calls](07-stored-kerning/v1/calls.jsonl) |
| V1-010 | Dedicated stored-kerning reads return a whole LTR master despite a “bounded” description; no pair/direction selector or limit. Glyph keys are native IDs without a public dedicated ID/name mapping. | Contract/workflow limitations; deferred, no fix | [Report 07 catalog](07-stored-kerning/v1/catalog.json), [208-record batch and public ID mapping](07-stored-kerning/v1/calls.jsonl), [report](07-stored-kerning/report.md) |
| V1-011 | The uninstrumented stored-kerning request proxy after an in-memory edit misses p95: 54.665 ms (n=36), max 62.684 ms. Native dirty flag was false in this initial setup; the separate explicitly dirty control passes. | Measured threshold miss; native cause unverified; deferred | [Report 07 initial profiles](07-stored-kerning/v1/facts.json), [explicitly dirty control](07-stored-kerning/v1-dirty-control/facts.json) |

V1-001 reproduction: open the eight Report 03 copies. `list_open_fonts` initially identifies `07-dirty.glyphs` at index 1. Bring that document forward using Glyphs' Window menu. A fresh list now places it at index 0 and `05-trial-4.glyphs` at index 1. Reading `get_font_glyphs(font_index=1)` returns the latter path and A's unchanged `export=true`; the dirty target has `export=false`. The follow-up agent step reused the earlier index even though its preflight contained the new mapping. This is an agent guard failure combined with positional targeting and the catalog's earlier stable-index guidance. It must not be presented as a wrong property value returned for the correct font. The separately resolved public probe used index 0 and correctly observed the dirty target's changed flag. No write was sent to the wrong font.

V1-002 reproduction: set the native server to free loopback port 9682, initialize and call `get_font_glyphs`. The response's `showHttpUrl` and `showMarkdown` use 9680. These links were recorded but not followed. The server was stopped and restored to port 9680, debug off, auto-start on after the test.

V1-003 reproduction: request ten known glyphs' metadata via the narrowest dedicated tool that includes export state, `get_font_glyphs`. Its sole font selector yields all 111 glyphs with additional fields and three navigation-link representations per glyph. The tested response is complete and accurate; this finding concerns scope control, description accuracy and response cost, not data loss. The common tokenizer estimates 26,401 returned-data tokens for the recorded timed response. This is not billed model usage. A custom Python route or client-side filtering was not measured as a replacement implementation.

No fixes, patches, installation changes or release actions are included. Revisit only in separately requested v1 work. Report 03's active recommendations concern v2.

Report 04 update, 2026-09-10: all 1,040 timed master ID/name fields were correct,
and the unsaved duplicate-name control returned the correct distinct IDs. V1-004
is an HTTP request-proxy finding, not proof of slow native callbacks; maxima were
120.651 ms idle and 73.113 ms post-edit. The test used 15 open disposable copies
and fresh positional-index resolution. The earlier targeting issue is not
cleared. One stale accessibility index failed while setting the temporary port;
it was an agent/UI setup error and is retained in the
[UI log](04-master-identification/ui-calls.jsonl). Glyphs 3.5's fifteen source-build
warnings are recorded as a host difference, not an MCP defect. V1 was stopped and
restored to port 9680, debug off, auto-start on; its 730 inventoried files are
unchanged. No v1 implementation change was made.

Report 05 update, 2026-09-10: v1 completed the scalar/bounds task accurately via
its documented public read-only Python fallback: 6,150/6,150 values exact. This
does not clear its dedicated-tool limitations. `get_glyph_details` intentionally
returns null bearings because `_get_sidebearing` avoids a known Glyphs 3 hang
risk after component writes. The defect is `get_glyph_paths` converting that
unknown result with `or 0`: the negative Light layer returned 0/0, while native
displayed values were −40.13/−30.63 and physical bounds implied
−40.125/−30.625. The clean-read fallback proof does not qualify native getters
after component edits or justify removing the existing safeguard.

The path tool's description also labels width/bearings as integers despite
fractional returned widths/coordinates; retain this for a later documentation
review. Dedicated tools lacked vertical values, bounds and metrics keys for the
full measurement task, so the fallback and its cost are explicitly reported.
Incorrect fixed-port navigation links recur as V1-002. V1-006 used 20 idle
samples and 10 post-edit samples over 2.181 seconds; public code execution and
different host load contribute to the proxy, and native callback time was not
measured. All 730 inventoried files remain unchanged. Temporary setup scripts
were removed, disposable edits discarded, and port 9680/stopped/debug-off/
auto-start-on restored. No v1 fix was made.


Report 06 update, 2026-09-10: v1 passed all 30 common timed selection values and
all 1,295 detailed timed node entries. It correctly excluded anchors, components
and guides; no count repair was needed. V1-007 is the context tool iterating
`font.selectedLayers` when the native value is absent. The separate node tool
returns a useful no-active-layer error in that case. V1-008 is distinct: a Font
View glyph selection supplies `selectedLayers[0]`, which the node tool mistakes
for Edit View context. Native `editView: false` is retained in the acknowledgement.
No v1 code or skill was fixed. Its 730 runtime files and source fixtures remain
unchanged. All test documents are closed and temporary helper files removed.
After the Mac was unlocked, v1 was restored to its original stopped/9680 configuration.
See Report 06’s cleanup-final.json and v1-panel-restored.txt. Its implementation remains unchanged.

Report 07 update, September 10 local / September 11 UTC, 2026: all 560 timed
requested values and all 1,512 returned native table records across the first,
warm-up and timed trials are exact. Completing a named-pair task requires a
separate bounded public `execute_code_with_context` ID mapping; independent
verification helpers never supply this mapping to the task. RTL and vertical
read correctly through separately labelled public native-code controls, so the
dedicated tool's LTR restriction is an MCP surface limitation, not a Glyphs 3.5
host limitation. The dedicated function reads `font.kerning.get(master_id, {})`
without checking that the master exists, explaining V1-009. Its `ok: true` /
`status: success` response for `does-not-exist` is retained, not treated as an
empty-font success. V1-010 concerns scope and interpretability, not incorrect
stored values. No implementation correction was made.

V1-011 is a sequential HTTP-proxy sample, not measured native callback time.
After the harness explicitly marks a fresh disposable document edited using the
native document change notification, its p95/max are 44.650/48.087 ms (n=39),
with the unsaved value preserved and source bytes unchanged. This does not erase
the earlier proxy miss. All 730 inventoried runtime files are unchanged, all
owned fonts are closed, temporary scripts are removed, and the original stopped
port 9680 / debug-off / auto-start-on configuration is restored. Report 07's
[cleanup evidence](07-stored-kerning/cleanup-and-ui.json) records restoration.

**P08 update — 11 September 2026; no v1 fixes.** The [fresh width comparison](08-width-changes/report.md) passed all 495 timed widths, all 495 restored widths and 29 separate v1 controls. The dedicated integer-width schema correctly rejects fractional targets and booleans; fractional width is a surface limitation, not a newly demonstrated host defect. The first two v1 attempts failed because the agent's harness misparsed response shapes; neither wrote a font. These are retained in P08 and are not v1 implementation failures. Native Undo/Redo was verified through documented public code invoking existing managers; no custom history was introduced.

**P08 cleanup observation, cause unclassified:** after testing and closing all owned fonts, native UI access timed out while restoring the original server port. The persisted preference was already 9680 and the temporary listener was stopped. A [two-second process sample](08-width-changes/v1/cleanup-ui-sample.txt) observed AppKit window/view deallocation on the main thread. Glyphs 3 recovered without restart and the native panel confirmed stopped/9680, debug off, autostart on. Glyphs 4 also temporarily timed out during script reload, then recovered. This does not establish a v1 server defect or isolate the host/helper/accessibility contribution. Retain the observation for later investigation; do not fix v1 on this evidence. [UI evidence](08-width-changes/ui-evidence.json), [port-state capture](08-width-changes/cleanup-port-ui-timeout.json), [120-second idle observation](08-width-changes/post-run-stability.json).

V1's instrumented per-layer HTTP write p95 reached 68.33 ms for the 90-write profile, while native write p95 was 1.33 ms. This is a request-proxy miss under recorded load, not a native write-budget failure. All 730 inventoried runtime files, skills and source fixtures remain unchanged. No user font was opened or changed; temporary files/menu entries are removed and the original server configuration is restored.

**VC01 offline review — 11 September 2026; no v1 fixes.** The packaged v1 and
configured lean-v2 development skills contain identical scaffold helper/assets.
Both create valid Reporter scaffolds, reject existing outputs and reject Python
syntax errors. Both also accept a deliberately replaced but executable loader
during static validation: the existing `sdk-loader` check verifies executability,
not the pinned `assets/SOURCE.json` hash. The modified loader was never executed
or installed. Log this shared validation limitation for a later v1 review; only
a v2 correction is recommended here. `runtimeTested: false` is accurate, and
`--target both` must not be read as native compatibility evidence.

V1's skill provides better scaffold/docs instructions but mixes internal MCP
maintenance rules with ordinary plugin creation. This is a source-review
observation, not a demonstrated native coding-session failure. Its 641 installed
documentation pages match index checksums; native accuracy across all host
versions and live retrieval quality remain untested in VC01. No v1 process was
started/reconfigured. All 728 files inventoried beneath its Resources directory
and its inspected packaged development skill tree remain unchanged. See the
[VC01 review](VC01-plugin-creation/review-20260911/report.md) and its measured
offline evidence; this narrower inventory does not replace the earlier full
730-file bundle baseline.

**VC01 attribution follow-up — 11 September 2026; log only.** A fresh local
disposable `palette` creation using the frozen v1 helper omits the supplied SDK
licence and drops the SDK source URL from its replacement Python file. This is
an inherited scaffold limitation also present in the lean v2 candidate, not a
new v1 runtime failure. The plugin was never installed or executed. The helper
tree was unchanged before/after the probe; all 730 previously inventoried v1
runtime files and 54 packaged v1 skill files still match their baseline hashes.
No v1 fix or native retest was performed. See the [review findings and local
evidence](VC01-plugin-creation/review-followup-20260911/report.md).


VC01 update, 2026-09-11 — unchanged v1 1.11.0+c98c9840e87a on Glyphs 3.5 (3532).

- **V1-012, documentation retrieval:** `docs_search("GSLayer.selection")` and `docs_search("foregroundInViewCoords")` returned no results in this installed catalog; `ReporterPlugin` located the Reporter guide. Broad natural-language queries returned substantial irrelevant API material. Preserve as a bounded retrieval/skill finding, not proof that the underlying APIs or complete source documentation are absent. [Recorded calls](VC01-plugin-creation/native-20260911/v1-baseline/calls.jsonl), [knowledge queries](VC01-plugin-creation/native-20260911/v1-baseline/knowledge-searches.json). No fix.
- **V1-013, coding skill scope:** the version-matched development entry includes repository-specific typed-envelope/tool-registration guidance and unconditional no-install prose even when the task already authorizes native installation and iteration. The agent followed the explicit task authorization and did not ask again. This is an instruction-quality finding; it did not prevent the trial. [Frozen skill](VC01-plugin-creation/native-20260911/v1-baseline/skill.md). No fix.
- Return-to-design control: selected-node data was exact for core (3), batch (256), empty (0) and mixed (3) cases; captured font state was preserved. Font View with no selected glyph returned `No active layer/glyph open in Edit view`. That is an explicit unsupported context, not a new false-active-layer finding; it does not clear V1-008's different selected-glyph case. [Accuracy](VC01-plugin-creation/native-20260911/v1-baseline/return-to-design-accuracy.json).
- Native Selection Lens creation/revision, toggle and Undo/Redo passed. Trial files were removed and menu absence verified after relaunch; original stopped port 9680/auto-start preference restored. 730 runtime files and 54 packaged skill files match frozen hashes. V1 used the solution learned during v2, so fewer artifact attempts and short requests do not establish a coding-speed advantage.

VC01 finalization: v1's remote off-curve marker is now visibly verified after two native zoom-out steps, with unchanged captured font state. The temporary trial reporter was removed again and menu absence verified after relaunch; original stopped port 9680 and auto-start preference restored. No new v1 implementation finding or fix. [Visual proof](VC01-plugin-creation/native-20260911/v1-final/selection-fit-complete.png), [finalization](VC01-plugin-creation/native-20260911/finalization.json).


VC01 full native workflow benchmark, 12 September 2026 — log only; no v1 changes. [Complete report](VC01-plugin-creation/full-benchmark-20260912/report.md).

- V1-012 documentation misses reproduced: exact `GSLayer.selection` and `foregroundInViewCoords` return no results; Reporter guide remains available. Five timed native sessions plus a warm-up completed on Glyphs 3.5 (3532), runtime `1.11.0+c98c9840e87a`.
- **Host API difference:** Glyphs 3.5 does not expose `GSEditViewController.safeViewPort`; the disposable plugin required `graphicView().visibleRect()` placement. This is a host-specific artifact adaptation, not an MCP implementation fix. Original drawing failure retained in `full-benchmark-20260912/v1-warmup/`.
- **Shared native history observation:** the isolated scripted fractional edit/Undo control restores captured font data, objects and selection exactly, but target dirty=true remains when original dirty=false. Reproduced in both hosts; root cause unisolated, no MCP/Reporter attribution established. Redo restores the full moved state. This qualifies the earlier broad Undo-pass wording without rewriting its measurements.
- **Returned link endpoint:** v1 `get_selected_nodes` returned `showHttpUrl` links on port 9680 during a verified 9682 server run. Links were not followed. See `full-benchmark-20260912/v1-1/events.jsonl`; review later, do not fix now.
- The measured v1 selected-node route lacks compact counts for other selected objects and an explicit retained document-ID parameter; Font View returns an explicit unsupported-context error. No alternate v1 Python/tool workflow was tested, so this does not establish that v1 cannot achieve the broader outcome.
- **Correction to raw harness hypotheses:** the initially suspected Glyphs 3 native replacement failure and wrong screenshots came from benchmark helpers retaining an earlier application handle. They are not established v1 defects. Explicit app arguments and destination checks corrected the harness. Extra old-bundle archiving in timed v1 trials is measurement overhead; native Replace behavior remains unisolated.
- Final audit: all 730 v1 runtime files and 54 packaged skill files match frozen hashes. Temporary 9682 listener is gone; original 9680/auto-start-on/debug-off settings are restored, waiting for occupied port 9680. Temporary plugins/scripts removed and native unload verified.

P09 spacing comparison, 12 September 2026 — log only; no v1 fixes. [Report](09-spacing/report.md).

- **V1-014, spacing false success on installed Glyphs 3.5:** all 495 timed layer requests are reported applied, but zero meet the proposed spacing and native data remain unchanged. `_set_sidebearing` deliberately returns false for host major version 3; `_set_layer_metrics` ignores that result. Before/after sidebearing reads are null, yet the confirmed call reports success. This is an installed MCP guard/result-reporting failure, not proof Glyphs 3.5 cannot space. [Installed source excerpt](09-spacing/v1/installed-spacing-guard.txt), [timed evidence](09-spacing/v1/primary-warmup.json).
- **V1-015, protected fractional figure widths:** the automatic 81-layer control claims 75 applied; only 36 default/`.tf` figure layers actually change, rounding 600.125/650.125/700.125 to 600/650/700. Exact width preservation fails. Existing native Undo restores all captured data; no setter bypass or repair was added. [Controls](09-spacing/v1/controls.json), [independent native proof](09-spacing/v1/auto-control-proof.json).
- **Unexpected exit, cause unclassified:** after the timed runs and native profiles, Glyphs 3.5 became unavailable/exited. The user confirms they did not close it intentionally. No new `Glyphs*.ips` file was found. One relaunch allowed final native menu Undo/Redo checks to complete. Log for later attribution; do not call the exit a proven v1 server crash or claim the relaunch fixed it. [Failed UI-check start](09-spacing/v1/ui-start.txt), [reopened oracle identity](09-spacing/v1/native-ready.json), [final audit](09-spacing/final-audit.json).
- Native Edit-menu Undo/Redo of an actual figure-width mutation restores captured data/objects/hints exactly. Dirty=false still becomes true after Undo, reproducing the previously deferred native dirty-state observation. [UI checks](09-spacing/v1/ui.json).
- First-attempt harness correction: top-level `applied` was initially misparsed instead of `data.applied`, generating vacuous raw passes. [Adjudication](09-spacing/v1/first-adjudication.json) supersedes those rows; subsequent runs verify nonempty target sets and fail correctly. This parsing error belongs to the harness.
- All 730 runtime files and 54 packaged v1 skill files still match frozen hashes. The temporary oracle is stopped/removed, P09 fonts are closed, and original stopped port 9680 / autostart-on / debug-off settings are restored. V1 implementation is unchanged.

P10 kerning collision comparison, 12 September 2026 — log only; no v1 fixes. [Report](10-kerning-collision/report.md).

- **V1-016, no native Undo for actual kerning bumper writes:** all 14 primary trials apply the expected integer corrections, but native document Undo has zero available steps and restores 0/14 trials. The genuine Edit menu disables Undo/Redo; the separate UI control also reports no document or layer Undo history. Closing owned copies without Save is cleanup, not restoration. [Primary evidence](10-kerning-collision/v1/series-warmup.json), [UI/native proof](10-kerning-collision/v1/ui-effective.json). The installed setter directly changes the kerning dictionary; that is source evidence for investigation, not a completed root-cause fix.
- **V1-017, ambiguous skipped-pair diagnostics:** clear pairs, empty/non-overlapping outlines, missing glyphs and an unknown master return `ok=true` with `pairsSkippedMissing`. Exact non-mutation passes, but the result does not distinguish these causes. The existing small-dataset warning also appears with explicit pairs. [Controls](10-kerning-collision/v1/controls.json).
- **V1-018, repeated explicit proposals:** duplicate-pair dry runs return the same change twice; a 3,001-entry duplicate request returns 3,001 proposals despite `pair_limit=3000`. No large corresponding mutation was attempted. This finding concerns request/result bounds and duplicate reporting, not a claim that 3,001 distinct pairs were measured. [Controls](10-kerning-collision/v1/controls.json).
- **Native UI display discrepancy, cause unisolated:** after the Regular kerning application and master selection/zoom, the selected glyph's information box still displays group value −88.375, while native stored/effective reads both return −71 and exact contour clearance is 5.625. The canvas shows separated outlines. Do not assume all native rendering is stale or attribute this entirely to the MCP runtime. [UI observations](10-kerning-collision/ui-observations.json).
- Both versions miss the deliberately finer spike at a 10-unit sample step; v1 detects it in the 0.125-unit dry-run control. Its conservative integer rounding is documented policy, not a newly introduced precision regression. All 495 timed corrections meet that policy and preserve captured outlines, widths, metadata, classes and unmeasured peers.
- All 730 v1 runtime files and 54 packaged v1 skill files are unchanged. Temporary helper and fairness fonts are removed/closed, and stopped port 9680 / autostart-on / debug-off is restored. No new Glyphs crash report appears. [Final audit](10-kerning-collision/final-audit.json).

P11 start-node alignment comparison — log only; no v1 implementation changes. [Completed report](11-start-node-alignment/report.md).

- **V1-019, malformed cubic segment accepted:** a native CURVE endpoint without its required incoming controls passes review/dry-run/application. The actual native Bezier commands change after start-node rotation, despite unchanged node coordinates and unchanged Glyphs 3 layer bounds. V2 also accepts the malformed input, with a different initial host interpretation. This is a supported-input validation gap to investigate later, not a claim that valid start-node alignment fails. [Native before/after drawing evidence](11-start-node-alignment/v1/malformed.json).
- **V1-020, captured native responsiveness p95 exceeds target:** one instrumented batch has callback p95 81.59ms/max 92.23ms (n=60), main-queue lag p95 77.09ms/max 119.63ms (n=220), and 2.27 seconds after mutation. The <50ms p95 target fails; <200ms maximum passes. Probe-off/on status medians differ by about 20ms in a small sequential control; overhead, host load and callback granularity prevent a causal attribution or optimization recommendation. [Profile](11-start-node-alignment/v1/profile.json).
- **Undo-scope workflow ambiguity, not a general v1 Undo defect:** the first benchmark route called the native document Undo manager and got zero steps in 14 trials. Genuine Edit-menu Undo/Redo then passed straight and mixed cubic cases; the native glyph Undo manager through existing public scripting restored all 14 fresh repeated trials exactly. Original failed-route and failed profile-restoration evidence is preserved. No product fix was needed for the successful route. [Corrected first](11-start-node-alignment/v1/series-glyph-undo-first.json), [corrected repetitions](11-start-node-alignment/v1/series-glyph-undo-warmup.json), [native menu proof](11-start-node-alignment/v1/ui-align01.json). This finding does not rewrite the distinct P10 kerning-history result.
- **Agent/harness schema error:** the first review result's fingerprint was incorrectly read at top level rather than `data.planFingerprint`. Failure happened before application. It is not a v1 runtime failure. The selected-landmark phase difference is expected behavior: v1 puts the chosen landmark at native last; v2 retains the reference phase.
- Final accuracy: 462/462 requested rotations across 14 qualified workflows pass, exact native data/object restoration passes, 21 supported controls pass, and one asynchronous cancellation/discard case is unsupported by the installed v1 catalog. Dirty indicators remain true after native Undo, as previously deferred.
- All 730 v1 runtime files and 54 frozen v1 skill files remain unchanged. The helper/probe is stopped and removed, test fonts closed, temporary 9682 listener removed, and stopped port 9680 / auto-start-on / debug-off restored. No new Glyphs crash report appears. [Final audit](11-start-node-alignment/final-audit.json).

P12 slant comparison — log only; no v1 fixes. [Report](12-slant/report.md).

- **V1-021, new-backup hint-link resolution changes after Redo:** on both straight and mixed cubic cases, the three newly created `GMCP Backup: Italic First Pass angle=12.0` layers expose `None` origin/target hint links after acceptance, then actual node links after native Redo. The original target layers, objects, hints and drawing are preserved and restore exactly. Strict equality of the entire applied state fails because of the new backups. Lazy link resolution versus saved-file integrity is unisolated; do not claim permanent data loss. [Raw cubic proof](12-slant/v1/ui-slant01.json), [original-target adjudication](12-slant/adjudication.json).
- **V1-022, mixed path/component order safely blocked:** candidate review for a mixed path/component/path layer reports `topology_change_blocked:mixed:shapeOrder[1].index` (source 0, candidate 1). Reproduced in raw and the equivalent balanced-zero route, with exact non-mutation. An adapter indexing issue is a hypothesis; no bypass or fix was used. [Equivalent controls](12-slant/v1/matched-controls.json).
- **V1-023, long slant callbacks:** bounded batch profile has native callback p95/max 1,168.72ms (n=15), main-queue lag p95 260.24ms/max 1,182.91ms (n=166), including 2.26s after mutation. Both native responsiveness budgets fail. Callback timing includes Python/native candidate work; host differences, lower v1 load and probe overhead are recorded separately. [Profile](12-slant/v1/profile.json).
- **V1-024, unknown slant mode accepted:** an unknown mode string is accepted through fallback behavior in the control. Preserve as an input/diagnostic ambiguity for later review, without treating supported zero/31° angles as invalid inputs. [Controls](12-slant/v1/controls.json).
- **Policy clarification:** raw mode intentionally leaves anchors upright. The first raw attempts are retained; the equivalent route uses balanced mode with `curve_strength=0` and `stem_compensation=0`, and passes 14/14 primary workflows and 495/495 timed layer slants. Manual components with an unselected upright base do not receive the full linear shear; v1 expects an already italic base. Automatic-layer anchor behavior differs from v2's explicit skip policy. These scope differences are not generalized into a failed v1 slant engine.
- Native Edit-menu Undo/Redo restores original target data exactly; native glyph Undo restores all qualified trials and removes created backups. Dirty indicators remain true, reproducing the deferred shared finding. No dependent-component stale bounds appear in the matched v1 replay. Dirty live preview and stale-token rejection pass.
- All 730 v1 runtime files and 54 packaged skill files are preserved. Temporary helpers/probes are stopped and removed; native menu absence is verified. Test fonts are closed and the original stopped 9680 / auto-start-on / debug-off configuration is restored. No new Glyphs crash report appears. [Final audit](12-slant/final-audit.json).


## P13 — curvature display, September 13, 2026

[Paired report](13-curvature-display/report.md). No new v1 curvature geometry/edit-history defect: 14/14 primary trials and independent comb checks pass. Preserve the existing dirty-flag finding: all 14 immediate post-Undo states remain dirty despite exact stored-data restoration. Glyphs3 interprets node user-data layout differently from Glyphs4 in this fixture (6,228 field differences, geometry/non-node metadata identical); this is a host-format observation, not evidence of an MCP mutation. Text mode hides the comb by design while the getter retains historical `lastDraw` evidence. The focused skill can clarify this later. Four invalid overlay inputs are safely refused. V1 remains unchanged; temporary port9682 was restored to stopped9680, auto-start on/debug off.
