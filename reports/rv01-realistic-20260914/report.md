# RV01 — realistic font tasks on current lean v2

**The latest candidate is installed and the mixed task batch is complete.** Supported MCP editing works well on this real font. Native scripting can complete the wider outline and OpenType tasks, but it needs more accurate focused guidance. The executing LLM rates the overall mixed experience **3/5**, with supported MCP workflows nearer **4/5**. The obsolete configured OpenType skill scores **1/5**; the separately authorized native coding route works.

Final recorded assertions: **120 passed, 0 failed, 1 blocked and 1 unverified**. These are final checks after retained corrections, not a first-attempt success rate or an exhaustive production qualification. [Exact assertions](assertion-index.json) and [LLM judgment](llm-judgment.md) are separate.

## Installed baseline and font

The existing installer installed the prepared grouping candidate before benchmark edits. Glyphs **4.1 (4107)** reports:

- Bridge: `2.0.0-beta.1+8b74a8d27ae4`, full fingerprint `8b74a8d27ae48b6d3ef1a317439c925f488ae5c9a0e5f0733221f468b97af687`.
- Sidecar: `2.0.0-beta.1+82daa62ac227`, full fingerprint `82daa62ac2277b49920d38c2207541841bc8294c6abf987ecddce5056c34be79`.
- Product Beta 1, installer build 43, interface/protocol 1; **seven tools and five jobs** unchanged. [Installation receipt](installation.json), [loaded identity](runtime-installed.json), [catalog](catalog.json).

The user authorized saving the open unsaved document to a new copy before the normal relaunch. It was reopened successfully. The old file and saved copy are preserved; see [preserved work](preserved-unsaved-work.json).

The user selected an open-source font. The benchmark uses **Roboto Slab, 1,272 glyphs, three masters: Thin, Regular and Black**, from the [official repository at revision 67af3ce9c4ca574419e1295b6165a2eeee112e6e](https://github.com/googlefonts/robotoslab/tree/67af3ce9c4ca574419e1295b6165a2eeee112e6e). The source SHA-256 is `98bd0e35d9267ad101270727f18bb58b17b629160ccdf3d8a60f9a99d526e845`; [provenance and license](font-source/SOURCE.json) are included. Initial Dactylotype inventory was unused preparation, not a benchmark trial.

Glyphs displayed an older-producer notice and 20 component-alignment migration issues when opening the upstream font. Existing **Keep Position** choices were retained. Each route is verified against its own native post-load state; no claim is made that all historical import semantics are identical between CLI and GUI. Upstream source bytes remain unchanged.

## Task results

| Task | Route | Final result and quality finding |
|---|---|---|
| [T01: inspect real layers and selected nodes](tasks/T01/report.md) | MCP | Twelve layer IDs, advances and bounds and three node records agree exactly with native reads. Limits and empty selections are explicit. An extra missing-glyph control used the wrong selector key and remains unverified. |
| [T02: fractional width change](tasks/T02/report.md) | MCP | `o` advances change by exactly +12.375 in all masters; all other recorded data and objects preserved. Native Undo, Redo and discard restore/replay exact data. First Undo clears Edited. |
| [T03: repair contour starts](tasks/T03/report.md) | MCP | Two native node permutations restore the intentionally shifted masters to the original point correspondence. Geometry and identities preserved; discard exact. Native interpolation proof shows the practical benefit. |
| [T04: modify a handle](tasks/T04/report.md) | Native script | Exact +2.5 x on one off-curve in each master after correcting native rounding. This tests precise editing, not an established aesthetic improvement. |
| [T05: add a stem midpoint](tasks/T05/report.md) | Native script | Three exact collinear midpoints added; original polygon geometry unchanged. Extra points alone offer no demonstrated interpolation improvement. |
| [T06: remove redundant nodes](tasks/T06/report.md) | Native script | Three seeded midpoints removed exactly. A nonredundant-point control is rejected before partial edits. No general curve simplification claimed. |
| [T07: add strategic extrema](tasks/T07/report.md) | Native script | Native operation adds 7 on-curves and 14 handles per master. After precision protection, numerical deviation bounds are below 1.5e-12 units across six contours; compatibility retained. |
| [T08: corresponding cubic split](tasks/T08/report.md) | Native script | Adds a homologous midpoint in all masters. Master curves and native Light/Medium/Bold interpolations preserved within 6e-13 units. Better editability is plausible; improved drawing quality is not established. |
| [T09: create/run/revise a snippet](tasks/T09/report.md) | Native script | Scaffolder and static validation pass. Twelve native rows are exact; the actual revised file adds anchors and is read-only. Invalid inputs rejected. |
| [T10: review OpenType](tasks/T10/report.md) | Blocked skill; native control | Obsolete focused skill cannot run on the seven-tool interface. Authorized native review matches source code/flags and passes seven exported behavior cases. [Actual review](tasks/T10/review.md). |
| [T11: create and shape ss20](tasks/T11/report.md) | Native script | Native compile, actual TTF export and HarfBuzz shaping pass. Opt-in rule maps g to g.ss01. It intentionally duplicates existing ss01 for the test and should not ship as a new design feature. |
| [T12: diagnose bad feature code](tasks/T12/report.md) | Native script | Compiler identifies the missing glyph, ss20 and line 1; corrected code compiles. Prior feature source preserved. |

**Native scripts are not additional MCP capabilities.** The user explicitly requested creating and executing snippets and feature work. The public interface still has no arbitrary Python tool, feature editor or arbitrary topology-editing tool. No product code or skill was corrected during the measurements; only benchmark artifacts were revised.

![Native interpolation: deliberately misaligned starts and original correspondence](visuals/T03-native-interpolation.png)

![Actual exported ss20 off/on proof](visuals/T11.png)

## First-attempt findings retained

- Integer-grid rounding turned a +2.5 handle move into +3 and a 102.5 midpoint into 103. It also changed the first cubic split by **0.395–0.451 units despite matching topology**. Native extrema initially exceeded the 0.05-unit tolerance.
- A bounded temporary native rounding flag, already used by v2’s existing bridge, resolves these authored-script cases. Each target flag and the font grid settings are restored. This required source inspection: the offline search did not surface the needed native selector. The final artifacts do not import bridge code or add recovery machinery.
- The pinned export example uses `FontPath`, which fails in Glyphs 4. The actual keyword is `fontPath`; the other options likewise use lower camel case. The native export returned `None` while producing a valid TTF, so success was verified from the output and shaping, not inferred from the return value.
- The CLI feature flags can be callable. A truthy bound method misclassified the unused preliminary inventory. Calling the native getter gives flags that agree exactly with an independent source parser. Compiler results are tuples: `(False, error)` must not be treated as success merely because the tuple is truthy.
- Five relevant installed lean skills match current source and packaged copies. The configured OpenType skill is an **orphaned older instruction set**, absent from the current lean payload. It names `get_server_info`, `apiMajor == 2`, `read_document`, `preview_change`, and `execute_python`. This mismatch remains recorded, not silently fixed.
- The agent’s extra missing-glyph control used `name` instead of the documented `id`. The server reported glyph `''` unavailable. No discovery or alternate-font substitution followed, but the intended named-glyph assertion was not demonstrated.

Raw `facts-first.json` files are early stage checks. [Final assertions](assertion-index.json) add the later precision/geometry checks and retain blocked/unverified status. In particular, early node-count passes alone are not the final geometry result.

## Measurements and limits

**29 instrumented public calls, two document discoveries.** Known IDs are reused. Initial connector checks and installation are recorded separately; this count is not every shell/UI/assistant call in the conversation. The native helper only sets up copies and reads proof, apart from temporary timing instrumentation. It does not complete the MCP jobs.

| Measurement | Observed result |
|---|---|
| Initial discovery + first 12-layer read | 2,125.61 ms; discovery alone 2,091.88 ms |
| Five known-target three-node reads | median **28.59 ms**, range **20.96–34.00 ms**, p95 **33.64 ms**, n=5 |
| Width-job public calls, mixed phases | median 31.83 ms, range 16.62–47.88 ms, n=7 |
| Start-node public calls, mixed phases | median 42.06 ms, range 13.39–654.42 ms, n=7; includes discovery |
| Known-target native dispatch callbacks | median 3.14 ms, maximum 10.74 ms, n=6 including warm-up |
| Observed main-queue lag | phase p95 2.14–8.50 ms; largest maximum 66.58 ms; phase n=101–111 |
| Corrected isolated native outline action | 1.23–5.97 ms, one sample per task; excludes load and oracle |
| Isolated feature creation + compile | 55.43 ms, n=1 |
| Corrected Regular TTF export | 387.11 ms, n=1 |

The 20 ms queue probe includes two seconds after measured mutations. These bounded windows satisfy the existing p95 <50 ms / maximum <200 ms targets. Dispatch callback timings **do not include separately scheduled native editing chunks**; no such direct edit-chunk measurement is claimed. Native script timings come from isolated Glyphs processes. Probe overhead was not separately calibrated.

This is **one complete exploratory agent attempt per task, with its corrections**, not first-attempt/warm-up/five full-session repetitions. The five read repeats are explicitly a same-document microbenchmark. Some isolated verification work overlapped live trials. Host load changed from approximately 6.24/11.74/15.52 to 3.94/7.90/11.26; there is no matched v1 run or performance-improvement claim. Per-task end-to-end agent time, all UI actions and actual billed tokens were not instrumented. First freeze to preservation audit was 35.8 minutes, including source selection, installation, preparation, corrections and verification; that is not pure execution time.

Token estimates use the previous benchmark’s **tiktoken 0.12.0 / o200k_base**, sorted compact JSON and one parsed response. A known-target three-node request is **55 tokens**, its response **171 tokens**. T02 uses **413 request + 1,743 response tokens** over seven instrumented calls; T03 **340 + 2,209**. Skills/artifact text costs and exact per-call statistics are in [measurements.json](measurements.json). These exclude reasoning, images, repeated conversation context and unlogged UI payloads. No actual token-saving or billed-usage claim is made.

## Judgment and justified actions

The LLM judge is **the executing agent**, not an independent or blinded rater. [Per-task scores and reasons](llm-judgment.md) distinguish final correctness evidence, design usefulness, focused-skill accuracy, workflow effort and delivery. The outcome is workable with friction, not a 5/5 objective.

1. **High priority: repair OpenType skill routing/setup.** Provide a current focused native-coding reference, retire the obsolete owned instruction path through existing setup rules, and explicitly separate native scripts from the seven MCP tools. No feature-editing MCP tool is justified yet.
2. **High priority: add a short precision recipe for native scripts.** Explain native rounding, explicit all-master scope, transient flag restoration and exact read-back. Preserve existing native operations and Undo mechanisms; do not add a topology engine or recovery system.
3. **Medium priority: add qualified Glyphs 4 API notes.** Cover lower-case export parameters, callable flags, compile result tuples and output verification. Keep pinned official source text intact and separate from project qualification notes.
4. **Small agent/harness correction:** use `id` for glyph selectors. A clearer invalid-selector message is a possible lean validation improvement, but this benchmark does not justify broad schema changes.

No task established that indiscriminately adding nodes improves an already-correct font. The useful pattern is to identify a concrete correspondence or editability problem, use a native operation or a small explicit script, then inspect native interpolation and drawn geometry.

## Preservation and remaining UI check

[Final preservation audit](preservation.json): upstream source bytes, original Dactylotype files, the original unrelated test file, the newly preserved saved copy, configured skills and pre-existing source-worktree changes are intact. Native checks preserve the recorded object identities and collateral data. Edited real layers have **zero hints**, so populated-hint preservation is unverified. No new Glyphs crash report was found; normal autosaving remained **8 seconds**.

Both GUI benchmark copies are closed, the timing hook restored and temporary helper removed. V1 is unchanged. The Mac locked during the final UI check, leaving only Scripts-menu refresh and restored-window confirmation pending. The native cleanup record already confirms the protected document is unchanged. No release was published.
