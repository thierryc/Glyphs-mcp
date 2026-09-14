# P13 — curvature display: installed lean v2 versus v1

13 September 2026 local time; timestamps use UTC, continuing into September 14.

**Both versions pass all 14 primary display/edit/history workflows and exact captured-data restoration.** Each version also passes 117,544 independent stroke-coordinate checks. V1 completes this automated agent workflow more effectively through its public overlay controls and clearer coverage evidence. V2's companion draws accurate geometry and supports text-mode display, but silently omits components and cubics beyond its 128-cubic bound. Its native queue probe also exceeds the maximum-lag target once. These findings remain separate from the historical autosave crash and Undo dirty-state issue.

No implementation, skill, release or installation was changed. The source baseline is lean `lit/v2-beta` commit `ffb3e1c5`, following checkpoint `2157efe2`. [Specification](test-spec.md), [structured facts](facts.json), [full accuracy results](accuracy.json).

## Baseline and scope

| Evidence | Lean v2 | Unchanged v1 |
|---|---|---|
| Host | Glyphs **4.1 (4107)**, `com.GeorgSeifert.Glyphs4`, PID14685 | Glyphs **3.5 (3532)**, `com.GeorgSeifert.Glyphs3`, PID43122 |
| Runtime | **2.0.0-beta.1**, installer43; sidecar `61c6975537ea`, bridge `bffc1729a4d7` | **1.11.0+c98c9840e87a** |
| Catalog | Existing **seven tools** | Existing **87 tools** |
| Curvature access | Independent **Curve Inspector** companion; native **View → Show Curve Inspector** | Public `set_curve_review_overlay` / `get_curve_review_overlay_state`, plus native **View → Show Glyphs MCP Curvature** |
| Test endpoint | `http://127.0.0.1:9680/mcp/`, unchanged | Temporary free loopback port9682; restored to stopped port9680 afterward |

Sidecar SHA-256 is `61c6975537eabcd1b015df6ed8f754a45616da11c3c1106a766410ed88c779ae`; bridge is `bffc1729a4d7e8856c807629efa9022c14907d389134d78194c28a9949463e9b`; v1 is `c98c9840e87a9bb7773b8fe643f21e86400323874a35c695e8ad01eb5a46bacc`. Catalogs, handshakes and identity requests are saved in each arm. The v2 companion advertises manifest version **0.1.0** independently of the product release. Its native module path and eight installed file checksums are recorded; it does not advertise its own initialization-time code fingerprint. Do not mistake its component manifest version for an old sidecar. [Frozen identities and receipt](freeze.json), [v2 native identity](v2/native-ready.json), [v1 native identity](v1/native-ready.json), [final status](final-status.json).

The installed global lean entry and focused outlines skill were tested first. Their intent route is correct: no imaginary curvature MCP command, job or Python tool was introduced. The available packaged v1 outlines skill was used for the separately identified v1 connection. Its curvature-only control was selected explicitly; optional curve-event markers and candidate sessions are outside this shared outcome. Entry/focused instructions were loaded once, and fresh copies were identified through public discovery. Identity/catalog setup repeats are qualification checks, not a recommendation to repeat agent setup.

## Fixture and method

The reproducible [native generator](fixture.py) produces [CurvatureTest.glyphs](CurvatureTest.glyphs), SHA-256 `6114ebb3b2c445b1f52b128c5cf6fcf84e70ca4fac9d008f4d4e0b70b5c68f8b`. Two native generations were identical. It has three fixed master IDs, fractional positions/advances, node names/user data, anchors, three-cubic and 40-cubic cases, a 129-cubic boundary, straight/empty layers, mixed path/component layers and components alone. Fresh disposable files were used for first attempt, one warm-up and five timed trials **per size and version**. V2 ran first; agent familiarity therefore favors the later v1 arm.

Native geometry, metrics and stored fields outside node user data agree exactly across hosts. Glyphs3 exposes node user data through a different dictionary layout: 6,228 field differences are retained as a **host-format interpretation difference**. Preservation is checked against each host's own native baseline; this is not a finding that MCP edited the metadata. [Native agreement](native-agreement.json).

Public tools/UI perform the task. The temporary [native oracle](NativeQualification.py) opens only disposable fonts, selects the test layer/node and reads data, native identities and actual reporter caches. It never activates, refreshes, edits or performs Undo for the reporter. Node movement and Undo/Redo are genuine native UI actions; v2 toggles are menu actions, and v1 toggles are public MCP calls. [Recorded UI replay](ui-replay.js), [v2 actions](v2/ui-actions.json), [v1 actions](v1/ui-actions.json), [v2 calls](v2/calls.jsonl), [v1 calls](v1/calls.jsonl).

The independent oracle evaluates Bézier positions, derivatives, signed curvature, right-normal placement and the 0.12em clamp with tolerance **1e-9**. Unchanged/restored stored data and object identities require exact equality. The fixture uses open cubic contours. Closed-contour wraparound is not new native evidence from this run. Zero hint objects occur in this fixture, so it does not add new hint-reference coverage. Representative native screenshots establish visible rendering separately from cache correctness; every timed trial also has native numeric evidence. Application restart/startup restoration was not retested: this case changed no installed companion and did not authorize a crash recovery restart. Display activation has no preparation job, cancellation or `discard_job`; its reversal is disabling the reporter, plus native Undo for the test nudge.

## Correctness and visual results

| Assertion | V2 | V1 |
|---|---|---|
| First/warm-up/five repeats, both sizes | **14/14 pass** | **14/14 pass** |
| Selected off-curve nudge | Exactly **+1 x**, preserved other stored fields | Same |
| Refresh, native Undo, Redo, final Undo | Correct comb and exact original data/objects | Same |
| Independent stroke-coordinate checks | **117,544 pass**, max error **1.36e-13** | **117,544 pass**, max error **2.28e-13** |
| Disable/re-enable unchanged layer | Correct; old comb does not remain drawn when disabled | Same |
| Light/Regular/Bold switching | Correct distinct layer/geometry without reporter toggle | Same |
| Straight/empty layers | Zero strokes; no previous-layer comb | Same |
| Mixed/components-only | Only direct paths shown; omission not explained in display/skill | Same raw-path scope; public state reports omitted component count |
| 129-cubic layer | **128 represented**, 1 omitted; no partial-coverage indication | **129 represented**, reduced sampling explicitly reported |
| Font View | No residual comb | Same |
| Text mode | Comb remains on the selected layer | Comb intentionally hidden; native outlines remain, last-draw state is historical |
| Return to editing, pan, zoom | Visible native outlines and comb retained/refreshed | Same |
| Stored-data/identity checks across 14 captured controls | **14/14 pass** | **14/14 pass** |
| Undo dirty flag immediately after primary restoration | **0/14 clean**; data is restored exactly | **0/14 clean**; same distinction |

The primary small case has **152 strokes at 51 samples/cubic**; the dense case has **1,947 strokes at 49 samples/cubic** in both versions. At 129 cubics, v2 shows **1,878 strokes from 128 cubics**, versus v1's **1,892 from 129**, both at 15 samples/cubic. `strokeCapReached=false` in v2 describes the 2,000-stroke budget; it does **not** establish complete cubic coverage. The missing evidence is the extraction-limit/omission notice. V1 also reports magnitude clamping and sampling reduction. [V2 boundary](v2/control-overLimit.json), [v1 boundary/public state](v1/control-overLimit.json), [mixed v2](v2/control-mixed.json), [mixed v1](v1/control-mixed.json).

Four invalid v1 requests are safely refused: unknown overlay, empty list, duplicate overlay and an invalid boolean. The first three return explicit tool errors; the fourth is an MCP input-schema error. They are expected refusals, not transport failures or font edits. V2 has no equivalent public overlay-parameter contract to test. [Invalid-input evidence](v1/invalid-inputs.json).

Visual judgment: both combs are useful for locating sign changes and uneven curvature while keeping the native outlines visible. The dense fixture is crowded, and clamping limits quantitative interpretation. V2's text-mode visibility is useful; v1's explicit legend and public warnings make its limits easier to explain. This is not a test of interpolation quality or a claim that uniform-looking combs make a well-designed glyph.

![V2 small curvature display](visuals/v2-first-small-enabled.png)

![V1 small curvature display](visuals/v1-first-small-enabled.png)

[V2 dense](visuals/v2-first-dense-enabled.png), [v1 dense](visuals/v1-first-dense-enabled.png), [v2 text mode](visuals/v2-text-mode.png), [v1 text mode](visuals/v1-text-mode.png), [v2 Font View](visuals/v2-font-view.png), [v1 Font View](visuals/v1-font-view.png). Different host palettes/reporters remain visible and were preserved, not silently normalized.

## Timing and cost

These are **automated complete workflow replays**: fit/select, enable, verify, nudge, verify, Undo/Redo/final Undo, disable/re-enable/disable, and independent verification. They include native oracle and UI automation/AX waits; they exclude fixture creation/open/close, identity/catalog setup, reasoning and report writing. Initial discovery is added in the second row for each size, never silently excluded from that total. Five samples per row; nearest-rank p95 equals the maximum. These are not native rendering latency measurements.

| Workflow | V2 median; range; p95/max | V1 median; range; p95/max |
|---|---|---|
| Small, retained target | **13.434 s**; 13.103–13.915; 13.915 | **9.747 s**; 9.554–9.789; 9.789 |
| Small + initial discovery | **13.616 s**; 13.248–13.951; 13.951 | **9.830 s**; 9.612–9.843; 9.843 |
| Dense, retained target | **16.980 s**; 16.417–17.219; 17.219 | **10.941 s**; 10.825–11.238; 11.238 |
| Dense + initial discovery | **17.012 s**; 16.558–17.368; 17.368 | **11.017 s**; 10.877–11.284; 11.284 |

Each timed v2 replay uses **15 UI actions** plus one initial public discovery. V1 uses **seven UI actions**, four public toggles, two public overlay-state reads, and one discovery. Identity/catalog qualification is excluded from those per-workflow counts. No retry occurred in the primary replay series. Timed load averages ranged **8.68–37.09 small / 7.58–12.30 dense** for v2 and **5.74–8.08 / 7.29–11.08** for v1. V2 had the original unrelated control plus its target open; v1 started with no user document and had its target only. WindowServer, Glyphs and unrelated background work contributed load. This was **not a matched-load causal comparison**. Fewer UI round trips explain an observed workflow advantage for v1; they do not prove its native geometry code is faster.

The manually paced first small trials took **177.06 s v2 / 165.79 s v1** from recorded target-ready state to final trial recording. The first saved visible evidence appears at **70.44 / 99.92 s**, including agent/orchestration pauses. These are conservative artifact timestamps, **not time-to-first-pixel measurements**. V2's initial canvas needed native Zoom to Active Layer. First attempts and warm-ups are preserved and excluded from the five-sample medians. Setup mistakes listed below occurred before the first complete trial and are not erased from agent effort.

All harness HTTP requests: v2 **n34**, median **135.39 ms**, range **32.49–258.11**, p95 **222.27**; v1 **n128**, median **20.01 ms**, range **7.97–123.24**, p95 **76.16**. V2's mix is identity/discovery; v1's includes overlay calls and four invalid-input controls. These heterogeneous HTTP round trips are **responsiveness proxies**, not directly comparable native callback timings. Final connector cleanup checks are recorded separately in `final-status.json` / `final-documents.json`.

The corrected ten-second native probe measures original functions, with the heavy accuracy trace disabled. It retains more than two seconds after the final recorded callback: **7.08 s v2 / 8.75 s v1**.

| Native measurement | n | Median ms | p95 / max ms | Result against p95<50 / max<200 |
|---|---:|---:|---:|---|
| V2 drawing callback | 8 | 8.67 | 10.47 / 10.47 | Pass in sample |
| V2 native cubic extraction | 18 | 2.69 | 5.65 / 5.65 | Pass in sample |
| V2 background comb worker | 2 | 3.08 | 3.11 / 3.11 | Background work; not a main-queue budget |
| V1 drawing + analysis callback | 2 | 28.29 | 28.30 / 28.30 | Pass in small sample |
| V2 main-queue timer lag | 714 | 1.24 | 2.01 / **382.49** | **Maximum fails** |
| V1 main-queue timer lag | 851 | 1.24 | 1.78 / 113.51 | Pass in sample |

The isolated timer samples include automation/host scheduling effects. Hook/probe overhead was not isolated with a matched on/off control; native sample counts are small. The 382 ms tail is real captured lag, but attribution is **unverified**. No cache, thread, watcher or Undo change is justified from this sample. [V2 timings](v2/native-timing.json), [v1 timings](v1/native-timing.json).

Token method is the established **tiktoken0.12.0 / o200k_base**, compact sorted literal-Unicode request `{name,arguments}` plus parsed MCP response. Per timed workflow including discovery, the MCP-only estimate is **159–162 small / 156–163 dense** for v2 and **1,833 / 1,965** for v1. **These are not equivalent total agent-context costs:** v2's actual curvature task uses UI rather than MCP, and UI screenshots, replay code and native oracle payloads are excluded from these numbers. No total-token savings claim is supported. Actual billed usage is unavailable. Skill text costs: v2 entry **817**, v2 outlines **588**, v1 outlines **2,306** tokens, loaded once. [Token/count details](facts.json).

## Agent and skill judgment

Scores use the established 1–5 scale and assess observed usability, not a score target.

| Dimension | V2 | V1 | Observed evidence |
|---|---:|---:|---|
| Discovery | 3 | 4 | V2 correctly routes to its companion, but the focused skill omits the exact View-menu label; v1 names its public control and menu path. |
| Instruction accuracy | 3 | 4 | V2's lean workflow is correct but omits raw-path-only scope, the 128-cubic limit, reduced sampling and clamp interpretation. V1 documents defaults, colors and omitted components. |
| Evidence clarity | 2 | 4 | V2's partial display has no coverage notice; establishing the omission required native verification. V1 returns counts and warnings through normal public tools. |
| Recovery guidance | 3 | 3 | Both can disable/re-enable and restore native edits; neither focused skill clearly explains the observed text-tool behavior and stale/historical last-draw evidence. V2's separate crash reference correctly preserves ordinary autosaving. |
| Workflow effort | 3 | 4 | V2 needs 15 UI actions per replay; v1 needs seven plus six direct overlay calls and produces reviewable status. |

The current v2 focused invocation prompt sends the agent to `$glyphs` to identify the connection, while its body correctly says to reuse retained context. A focused curvature reference can make the continuation route and exact menu action clearer without expanding the entry. Keep the invocation policy unchanged. V1's broad outlines skill contains unrelated candidate/editing instructions; only its curvature section was needed here. There was no baseline skill correction or fallback to an earlier private v2 workflow.

Agent delivery in this run had avoidable laboratory friction: a GlyphsLib draft was rejected by Glyphs, the native writer needed the Glyphs4 shape collection, the oracle initially failed to call `activeLayer()`, and a stale finish request stopped its first restart. The first native timing probe then raised **PyObjC BadPrototypeError** while restoring a callback without `objc.python_method`. Glyphs remained running; the dialog was dismissed without sending a report, original callback identity was manually restored and verified, and the corrected probe passed restoration. The failed timing sample is excluded, not relabelled as a product crash or successful timing trial. [Failed probe and exact cleanup](v2/native-timing-failed.json), [corrected source](NativeTiming.py), [explicit recovery](NativeTimingRestore.py). The initial UI port-field attempt also used a stale index and was corrected before changing the setting. These are agent/harness errors, not v1/v2 repair findings.

## Conclusion and justified actions

**V1 completed this concrete agent workflow more effectively**: accurate shared output, fewer UI actions, faster observed replays and better normal-access coverage evidence. V2's sampled geometry, native editing coexistence and exact preservation are sound; its compact skill/companion route needs clearer limitations and better display feedback. Text-mode rendering is a useful v2 difference. Native drawing timings and HTTP tails do not support a general architecture-speed verdict.

1. **High value, small scope:** add a focused v2 curvature reference with the exact menu action, color meaning, raw-path/component scope, 128-cubic bound, sampling/clamp limits, native view/Undo checks, and retained-context guidance. Link it from the compact outlines skill; synchronize the managed copies when implemented.
2. **High value, bounded companion change:** show a compact partial-coverage/component-omission notice using the existing visible-layer refresh/cache. Preserve the 128-cubic and 2,000-stroke bounds. A bounded look-ahead may establish “more than 128” without pretending to count every curve. Do not traverse a full font or add an MCP tool. Keep drawing display-only.
3. **Separate investigation:** retain the queue-tail failure and dirty-state finding. Measure comparable host/UI load and probe overhead before recommending a runtime optimization. No new cache/watch service or Undo machinery.

[Concrete v2 follow-up scope](v2-actions.md). No action above is implemented by this report. V1 findings are logged for later without fixes.

Cleanup passes: **32 disposable source files** unchanged; **34 sidecar, 29 bridge, eight companion, 952 lean-source, 1,731 global-skill, 77 configured-plugin-skill, 730 v1-runtime, 54 v1-skill and 451 protected Dactylotype files** retain frozen checksums. All test fonts closed, original reporter selections restored, five exact temporary scripts removed and menu absence verified. V1 is stopped on its original port9680, auto-start on/debug off. V2 retains only its original clean nine-glyph control, zero active jobs/native operations and unchanged live fingerprints. Autosaving remains **8.0 seconds in both hosts**. [Final audit](final-audit.json), [native v2 cleanup](v2/native-finish.json), [native v1 cleanup](v1/native-finish.json), [script removal](script-cleanup.json), [menu check](menu-cleanup.json).

The original PIDs survived **191.43 seconds after the final v1 cleanup**, with no new crash report. This bounded observation does not resolve the historical autosave crash. P13's paired benchmark is complete **with findings and the stated timing limitations**; review the proposed lean v2 follow-up before implementing it.
