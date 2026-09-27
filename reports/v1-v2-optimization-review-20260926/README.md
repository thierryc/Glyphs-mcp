# V1 → current v2: complete tool and workflow optimization review

26 September 2026. Review only: no runtime implementation, installation, font edit, save, restart, commit or publication.

**The best next simplification is one result workflow for font mutations, with execution appropriate to each operation.** Share baseline validation, exact scope, job identity, progress, verification and Keep/Save/recovery actions. Move simple typed edits off whole-font worker preparation. Keep expensive analysis and export outside the editor. Do not replace tested algorithms with newly generated Python merely because Python can call the same native API.

## Baseline and completeness

- V1: local release tag **v1.11.1**, commit `590053fedd7bcab13a2027fb3bce99b724072b57`. Its authoritative tool catalog is byte-identical to v1.11.0: **87 active tools, 76 model+app and 11 app-only**. The preserved website documentation is explicitly the v1.11.0 snapshot.
- V2: current working source, **12 public tools**, **11 job kinds when capabilities are available**, and **18 recognized closed native actions**. Runtime availability can be narrower than the source registry. The latest automatic-Keep source/build is not yet installed or visually qualified.
- Every v1 tool appears exactly once in [the 87-tool comparison](v1-tool-map.md), also available as [CSV](v1-tool-map.csv). All 12 current tools and 11 jobs are assessed below. The 39-group historical audit supplies the inventory, not its now-obsolete v2 availability judgments.
- This is a source/contract/evidence review. It does not rerun v1, establish fresh paired speedups, qualify every script recipe or complete previously blocked native gates. V1 historical benchmarks used Glyphs 3.5; the current native tests use Glyphs 4.1, so host differences matter.

## What improved, and what did not

V1 already had powerful live Python (`execute_code` and `execute_code_with_context`) and direct typed setters. Live scripting itself is not a new v2 advantage. V2 improves the lifecycle: exact document bindings, retained request identity, saved-baseline guards, no automatic replay, bounded evidence and explicit recovery. V1 often required fewer calls for small direct edits, though fewer calls do not prove faster or safer execution in all cases.

V2's saved-version recovery is simpler than serializing arbitrary script effects, but coarser: it replaces every subsequent unsaved font edit and clears Undo. It does not recover files written by scripts. Typed selective Undo/discard remains valuable for small changes amid other work; sharing the conversation does not require deleting it.

The twelve-tool count overstates how simple the interface has become. `read_entities` alone has **960 words / 7,283 characters** of tool description, and nine font-mutation job kinds sit behind generic dispatch. There are still two overlapping orchestration surfaces: low-level jobs and conversation workflows. Keep compatibility, but guide ordinary editing through one surface.

## Every current public tool

| Tool | Closest v1 behavior | Current assessment and optimization |
|---|---|---|
| `get_status` | `get_server_info` | Better capability/identity evidence. Use once per connection and after invalidation; do not precede every operation with it. Keep live health separate from reusable capability metadata. No script or saved baseline needed. |
| `list_documents` | `list_open_fonts`, part of selected-font context | Exact bindings improve targeting. Retain the intended binding until invalidated; avoid repetitive discovery. Never infer the intended font from list order. |
| `read_entities` | Many font/glyph/master/layer/selection/kerning/feature reads | Correct native read route for dirty and unsaved fonts. Batch known targets and request only needed fields. Add narrowly needed scalar/aggregate reads rather than running a mutating script just to inspect data. Pagination remains bounded, but one font-wide analysis should not require every page to pass through the model. Shorten routing prose by moving detailed selector examples into focused references without removing necessary schema constraints. |
| `start_job` | Dedicated review/proposal calls | Useful for diagnostics, exports and explicit low-level clients. Ordinary edit agents should use `start_edit_workflow`. Preparation should depend on the kind: simple setters do not all need a saved-font copy and a fresh worker process. Preserve non-executing script preparation. |
| `get_job` | Tool-specific report/candidate status | Keep for low-level diagnostics/artifacts. Use compact reads while running. Avoid duplicate polling by both the agent and card; reconcile the existing job after timeouts. Unchanged bridge observations should not rewrite identical durable job evidence. |
| `apply_job` | `apply_spacing`, `apply_kerning_bumper`, node setters and other apply calls | Already applies without saving. Retain typed guards, overwrite approvals where required and target verification. The problem is preparation and post-apply settlement, not a missing save-free apply operation. |
| `accept_job` | `save_font`, candidate acceptance and export publication | Currently combines font-result acceptance with Save, and also publishes export artifacts. Keep compatibility but distinguish Save font from Export files in conversation. Add a separate save-free completion action for typed edits through the existing workflow rather than making acceptance mean two different things silently. Correct the tool's blanket “Neither mode overwrites” wording: ordinary authorized Save updates its current file; Save As/export destination collisions are rejected. |
| `discard_job` | Candidate discard, task-specific Undo/cancel | Preserve selective typed recovery and cancellation. Use action-specific labels: Cancel preparation, Undo these changes, or Discard export. Saved-font reload must never silently replace selective Undo. |
| `save_document` | `save_font` | Stronger path/identity and completion receipts. Keep one save service, reuse actual authorization and verify completion. A clean baseline needs no preparatory Save. Saving an existing file and Save As to a new path need distinct wording. |
| `start_edit_workflow` | Several v1 review/apply/feedback flows | Make this the usual font-edit entry for both scripts and typed operations. Share target validation and saved-baseline handling; preserve preview intent and special existing-value approvals. No additional code-review requirement for authorized simple edits. |
| `get_edit_workflow` | Candidate status and feedback refresh | Keep compact evidence and optional Script details. Fix stale saved-state wording; memoized restoration display never authorizes reload. Add no automatic execution on reads. |
| `respond_edit_workflow` | Apply/accept/discard and feedback-plan actions | Generalize Keep without saving to typed jobs. Share revision/idempotency mechanics, but make recovery coverage explicit per action. Fix failed Wait opt-out before extending timed Keep. Action origin is evidence, not proof of a human click. |

Source: [server](../../src/sidecar/glyphs_mcp_sidecar/server.py), [conversation tool contract](../../src/sidecar/glyphs_mcp_sidecar/edit_workflow_ui.py), [workflow actions](../../src/sidecar/glyphs_mcp_sidecar/edit_workflow_state.py).

## Every current job kind

“Native candidate” below means a closed implementation reusing the shared runner; it does not mean exposing another arbitrary selector or asking the model to generate code for an already-supported typed operation. These are recommendations, not implemented or benchmarked speedups.

| Job kind | Current engine / v1 comparison | Disposition |
|---|---|---|
| `width_delta` | Saved-font copy, fresh worker, patch; v1 had direct exact width/sidebearing setters. Current delta reaches all stored layers unless constrained by glyph names. | **Highest-value native candidate.** Width arithmetic should not load a second whole font. Use exact layer/master scope; do not substitute all stored layers for a selected-master request. Retain cheap scalar verification and selective history. Native scripts already cover exact custom metrics under their different recovery contract. |
| `dimensions_edit` | Fresh worker for small explicit reference-metadata changes; not equivalent to v1 actual stem metrics. | **Highest-value native candidate.** Read and validate exact old/new fields natively, reuse the current overwrite-approval contract and typed history. Avoid full-font preparation for a handful of metadata values. |
| `native_action` | Executes a closed action on a saved copy, records projected before/after, then invokes it on the live target with recovery. Eighteen action names. | **High potential, qualify by action.** `set_glyph_color` and simple metadata/metrics actions are the first candidates. Cleanup, overlap removal, reinterpolation and feature generation can have wider dependencies or expensive invocations; retain exact scope and test before removing their preview/recovery work. Explicit previews remain proposals. Do not add a public fast/safe mode. |
| `outline_edit` | Typed path operations prepared on detached copies, then guarded native apply; replaces many direct v1 node/path setters. | **Optimize selectively.** Simple coordinates/transforms can prepare from bounded target state without a full-font worker. Keep topology/path guards, fractional precision and existing recovery. Complex topology changes need their real verification; a successful generic script is not equivalent. |
| `spacing` | External reference/area analysis plus a verified patch; subset of v1 spacing options. | **Keep the tested algorithm and external calculation.** Numeric “add 12.5 to LSB” is a native-edit task; “calculate spacing from references” is analysis. Improve batching, worker cost and result settlement rather than substituting raw setters for spacing quality. |
| `kerning_collision` | Explicit-pair sampled collision analysis plus exact stored exceptions; narrower than v1 automatic relevant-pair discovery. | **Keep external analysis.** Native scripts are suitable for explicit A/V values or group changes, not a replacement for collision/effective-kerning resolution. Batch requests and preserve direction, absent-vs-zero and class/exception semantics. |
| `start_nodes` | Joint contour-correspondence planning outside Glyphs; native reorder application. | **Keep correspondence logic.** Transport only the required contour data where feasible, rather than launching a font-sized job for trivial cases. An already-specified cyclic rotation is simpler than discovering correspondence. Never equate rotation with full master compatibility. |
| `slant` | External geometry preparation, optional stem correction, component transform handling; less than v1 balanced italic. | **Separate mechanical task from algorithmic task in routing.** A precise simple transform fits native execution. Preserve the qualified stem/component logic for the typed algorithm; avoid double-shearing selected component bases. No full optical-italic parity claim. |
| `python_script` | One live native route, per-target callbacks or whole scripts. V1 already had live Python. | **Keep and harden.** It is the right extension route for composed exact edits and unsupported native operations. Current 4,096 declared-surface limit is an implementation ceiling, not a universal capacity bound. Test larger work before replacing it; never truncate silently. |
| `feature_compile` | Saved-copy or live-editor diagnostic. Both currently require saved/clean state; v1 could invoke compilation through Python. | **Fix the workflow mismatch.** A live diagnostic should be able to verify a stopped, unsaved edit before Save/Keep, once ownership and nonmutation checks are qualified. Do not make users save broken feature source merely to validate it. Preserve the existing compiler-result interpretation and persisted-feature guards. |
| `font_export` | Worker build, artifact checks, staging and explicit publication. V1's dedicated Designspace/UFO exporter is a different deliverable. | **Keep external execution and staged output.** Whole-font Restore cannot undo exported files. Batch compatible build checks where useful; separate compile, binary tables and shaping evidence. Do not call TTF/OTF/WOFF support Designspace/UFO parity. |

Evidence: [worker dispatch](../../src/sidecar/glyphs_mcp_sidecar/native_worker.py), [one-shot worker](../../src/sidecar/glyphs_mcp_sidecar/worker.py), [whole-source copy](../../src/sidecar/glyphs_mcp_sidecar/source.py), [native action preparation](../../src/sidecar/glyphs_mcp_sidecar/native_action_job.py), [live compile guards](../../src/bridge/glyphs_mcp_bridge/core.py), [compile implementation](../../src/bridge/glyphs_mcp_bridge/feature_compile.py).

## Findings in priority order

1. **Typed editing cannot settle without saving or reversing.** Scripts have `finish_script`; typed applied workflows offer Save/Save As/discard and block later work. Extend explicit Keep through the existing lifecycle and reconciliation. Release the job without silently saving or undoing. Preserve native Undo where supported; describe whether wrapper recovery ends. Do not silently overload `accept_job`, whose existing callers expect persistence.
2. **Simple work pays for whole-font preparation.** Typed preparation copies the source and hashes original/copy/original, starts a one-shot Glyphs process, loads the font and constructs a patch. That architecture is justified for expensive analysis and isolated previews, but excessive for a width or color change. Use closed native implementations sharing the existing coordinator, not a second public execution mode.
3. **Verification sometimes forces persistence.** Both service and bridge reject dirty live compilation. This defeats “edit unsaved → verify → Keep/Save/Restore” for OpenType. Permit the existing guarded diagnostic against the exact stopped live state only after testing preservation and interaction with an unresolved script; do not bypass ownership checks or introduce broad live-font capture.
4. **The newest Wait action has a reproduced failure.** A host-rejected Wait is followed by a successful read of enabled state, restarting the countdown and issuing automatic Keep. Latch the local pause immediately, regardless of request success. The defect remains unfixed in this review.
5. **Saved-state wording can be false.** Result text uses execution-time `documentAfter`, despite a fresh document read. After a manual Save it can say unsaved; after later edits it can say saved. Use current observations and label historical evidence. This remains unfixed.
6. **History and polling still do avoidable work.** `JobStore.records()` sorts and deep-copies all retained records; mutation/status paths call it repeatedly. Workflow supervision scans all workflows four times a second, and applied `get_job` reads rewrite job state even without a changed native result. Maintain lightweight active indexes and skip unchanged writes, retaining old evidence and idempotency records. A synthetic prior review probe measured ~1 / 10.5 / 115 ms per records call for 10 / 100 / 1,000 completed records with 100 targets and 512 numeric params each; this is not editor latency.
7. **Generic Python is being mistaken for feature parity.** It restores access to APIs, not v1 Unicode allocation policy, compensated scaling, balanced italic, numerical curve reports, managed annotation groups or Designspace/UFO export. Reuse maintained recipes/algorithms where worthwhile; do not regenerate specialized engines in each conversation or mark them supported without native tests.
8. **Documentation remains too easy to drift.** The metadata-read reference still lists only five available fields despite added color/kerning fields. The command reference's blanket clean-preparation statement omits dirty script preparation. Large tool descriptions repeat workflow instructions. Keep one execution reference and small capability-specific references; preserve v1 documentation as history.

## The common result workflow and its limits

For a font edit: **resolve exact scope → establish the required baseline → execute without saving → verify → Keep without saving / Save / available recovery**. An in-scope edit request authorizes execution; explicit preview requests still wait. A clean saved baseline requires zero preparatory Save calls. Saving a dirty font requires actual authorization and verified completion. Saving always includes all current document edits.

The result card should use the same main actions for scripts and typed edits. Recovery labels must remain accurate: **Undo these changes** for selective typed recovery, **Restore saved version** for whole-font reload. The latter could be shared by additional native operations using the existing baseline service, but cannot silently replace the former. It is not always better: reloading a one-node edit also discards unrelated later work and clears Undo.

Keep-without-saving ends a workflow's restoration offer; it does not create a new saved baseline. A subsequent script still requires a clean saved baseline under the current contract. Therefore adding Keep alone does not eliminate inter-task saves. Compose a single authorized path/spacing/kerning task into one native invocation where it makes sense, with one baseline and one result. Never silently widen separate task scopes or retain an accumulating hidden transaction across unrelated work.

Read-only inspection should remain live, bounded and save-free. Do not route simple reads through `python_script`: its execution path marks the document changed and establishes a mutation/recovery lifecycle even if the source only prints data. Exports have their own file-publication actions; Keep/Restore font semantics do not fit them.

Automatic Keep is acknowledgement/settlement, not result validation and not an engine speedup. Keep it restricted to the requested successful-script case until the opt-out defect and installed-card gates pass. Do not spread the timer to every workflow as part of UI unification.

## Performance and capacity: what the evidence supports

From the last qualified native build, medians over five fresh-process runs:

| Backgrounds × contours | Direct callback loop, seconds | Native workflow, seconds |
|---|---:|---:|
| 100 × 1 | 0.010 | 0.316 |
| 1,000 × 1 | 0.103 | 0.576 |
| 4,096 × 1 | 0.418 | 1.866 |
| 100 × 12 | 0.111 | 0.601 |
| 500 × 12 | 0.560 | 1.109 |

These are not v1-versus-v2 timings. The loop excludes setup/cleanup; native workflow includes preparation, the fixture's authorized Save and dispatch/polling. Real-font path, explicit spacing and kerning were tested separately in both source formats. An explicit spacing adjustment is not the typed spacing algorithm, and explicit kerning setters are not collision analysis.

At 4,096 simple surfaces, native peak RSS was **206.3 MiB median, 195.1–324.8 MiB range**. Simple surface count alone does not predict memory or duration. Whole scripts with `targets:[]` can already traverse the entire font; the 4,096 ceiling constrains wrapper-declared manifests, not arbitrary Python effects. Selection limits, node limits, snapshot byte limits and read-page limits serve different purposes and should not be raised together.

The installed-client Run observations were **4.913 s and 5.615 s, n=1 each**. They are not a distribution or a matched comparison with the isolated loop. Measure model/tool orchestration, host approval delays, HTTP, native queue, execution and result delivery separately before choosing transport changes.

Measurement weaknesses remain: the bulk benchmark checks one node, not every target; measured scheduled chunks exclude some preparation/hashing/save/reload work; real-task RSS is cumulative across tasks; some measurements ran while the machine was doing other work. Preserve these limitations. No new speedup, memory bound, responsiveness guarantee or universal v2-over-v1 claim is supported.

For a future capacity qualification, include larger simple scopes, fewer very complex layers, large params, package I/O and long retained histories. Verify all target outcomes plus untouched controls, measure full main-thread latency, and preserve one logical job and one baseline. Oversized requests must fail before edits, never silently stop at a prefix.

Sources: [native qualification](../native-scripting-qualification-20260926/README.md), [benchmark driver](../../scripts/benchmark_saved_scripts_workflow.py), [earlier real-task evidence](../real-task-qualification-20260926/README.md). Historical paired v1/v2 reports remain historical; they do not measure the current scripting candidate.

## Recommended optimization order

1. Fix the reproduced Wait and current-saved-state defects; complete installed-card/action-origin qualification.
2. Add save-free settlement for typed results through the existing conversation actions; test Keep → next task and reconnects.
3. Remove unnecessary whole-font worker preparation from widths, Dimensions and simple closed native actions, with before/after benchmarks and preserved typed recovery.
4. Make live feature verification usable before Save/Keep under guarded ownership; retain the external build/export pipeline.
5. Reduce repeated polling, full-history copies, unchanged persistence writes and duplicated routing prose.
6. Measure larger bulk capacity and the remaining algorithmic preparation costs before expanding limits or changing worker architecture.

No new public tool, execution-mode switch, snapshot architecture, backup service, worker pool or speculative cache is needed to start. Keep typed algorithms where they provide tested behavior; use native Python for exact composed tasks and real capability gaps. Source review does not substitute for installed behavior, and automatic Keep does not substitute for verification.

The auto-Keep build remains uninstalled. The existing record of unrelated unsaved Dactylotype work and the pending save/close choice are unchanged by this review. Previous unperformed fault/overwrite probes and unattributed Run/Keep observations remain open; this report does not convert them into passed gates.
