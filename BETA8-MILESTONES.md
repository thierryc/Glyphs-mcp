# Beta 8 milestones: simpler and faster editing

Status: milestones 1–7 are complete locally, including installed qualification. Milestone 5’s final Codex card checks passed with user observations and matching server evidence; see its [qualification report](reports/beta8-milestone5/README.md). Milestone 8's exact kerning assignments and bounded language proofing are implemented, with focused tests and standalone native benchmarks passing. Its installation and actual-editor/client gates remain incomplete: macOS filesystem calls stalled during installation staging and the desktop build; see the [qualification and resumption record](reports/beta8-milestone8/RESUME.md). Git checkpoints and the font project template are milestone 6; consolidation is 7 and kerning is 8. The separate signed-update/component-migration qualification remains open.
Date: September 28, 2026.

[Milestone 1 delivery and qualification report](reports/beta8-milestone1/README.md):
tests-first implementation, 2,291 passing regressions (two skips), 150 passing
benchmark runs, and installed native execution/saving/cancellation/restoration.
The report preserves measured regressions, pauses and editor limitations.

The first milestone removes the native-script ceiling of 4,096 selected
surfaces. The following milestones reduce unnecessary preparation, cleanup,
polling and conversation work. Milestone 6 adds opt-in Git checkpoints and a
Git-enabled font project template. Milestone 8 restores exact typed kerning edits
and adds language-aware discovery and proofing. Each milestone is a separate
delivery with its own qualification gate.

## Delivery rule for every milestone

1. Write meaningful regression tests before changing implementation. Run them
   against the current code and record the expected failures. Preserve existing
   assertions for behavior that must remain unchanged.
2. Record the relevant current performance baseline, then make the smallest
   implementation change that satisfies the tests.
3. Run affected regression tests and native qualification where behavior depends
   on Glyphs. Update affected canonical guidance and regenerate its packaged
   mirror in the same milestone; do not defer accuracy fixes to milestone 7.
4. Report changed behavior, passing/failing tests, before/after measurements,
   installed-runtime identity where tested, and any unperformed checks.
5. Record completion before advancing. The user's September 27 continuation
   request authorizes proceeding to the next milestone and saving when needed
   if no issue prevents it. Resolve issues within the accepted scope; stop for
   an unresolved gate or a decision that needs the user. A blocked native gate
   remains incomplete; source tests do not replace it. Earlier per-milestone
   stop notes below describe the original staged delivery boundaries.

No mandatory user code-review step is added. Keep existing task authorization,
separate save authorization, optional Script details and explicit preview rules.
This plan does not itself execute a font edit, install a runtime, commit changes
or publish a release.

## Milestone 1 — Remove the native-script target-count ceiling

**Use case:** vertically flip paths in all 12,000 eligible Regular-master
backgrounds through one job, with one saved baseline and one result workflow.

### Tests first

- Accept 4,097, 10,000 and 20,000 eligible surfaces when the complete request fits
  the existing byte budget. Exercise explicit targets, named bulk selectors and
  `glyphs: "all"`; retain the 4,096 case as a regression control.
- Verify complete coverage and one callback per deduplicated surface. Preserve
  overlap rejection, exact master/document targeting, zero-eligible behavior,
  metadata/image-only eligibility and exact skipped counts with ten examples.
- Resolve missing layers/backgrounds without creating them. Include a fixture
  whose ordinary layer iterator fails if used, and verify native stored-layer
  access on a real incomplete-master fixture.
- Reject oversized requests before Python executes and before a prerequisite
  Save when the oversize is already knowable. Cover UTF-8 names, escaping, long
  identifiers, source, parameters, duplicated target data and the outer request
  envelope at the actual encoded byte boundary.
- Cancel during preparation and between callbacks; invalidate preparation when
  the document or manifest changes. Reads, previews, duplicate dispatch and
  reconnects must never run or replay Python.
- Keep unrelated typed-operation, read, source, parameter and output limits
  unchanged. Preserve clean-baseline zero-save behavior and separately
  authorized dirty-baseline saving.

### Implementation

- Remove native scripting's count checks from explicit target validation, bulk
  name validation, eligible-target resolution and execution-manifest validation.
  Do not replace 4,096 with a larger fixed count.
- Retain the existing **4 MiB complete internal request limit**, 128 KiB source,
  64 KiB parameters and 16,000-character output limit. Account for the actual
  bridge encoding, including options, manifest and envelope. Perform the full
  authoritative request check again immediately before dispatch.
- Account for manifest bytes incrementally so an enormous bulk selector does
  not build an unbounded list before failing. Avoid repeated whole-manifest
  serialization per target. Bound reports and ordinary progress responses too.
- Reuse stored-layer helpers and the existing preparation/job scheduler to
  resolve and revalidate targets in main-thread chunks. Cancellation and
  document-generation checks apply between chunks. Preparation stays read-only.
- Freeze exact target identities for Run. Keep one job, baseline and result;
  do not split work into separately saved jobs or silently process a prefix.
- Preserve callback batching, ownership, exactly-once reconciliation and
  incremental script cleanup. A running callback or whole script remains
  non-preemptible. Runtime failure can still leave partial edits for inspection.
- Keep twelve tools and `script.native.v1`. Update coordinated sidecar/bridge
  validation and guidance. A stale runtime must produce a clear compatibility
  error; do not evade rejection through a whole-script fallback.

This removes a count ceiling, not all resource bounds. A sufficiently large or
verbose manifest can still exceed 4 MiB. The message must explain the actual
byte constraint; it must not imply that the first 4,096 targets were edited.
Typed snapshot/patch limits and node limits remain separate future decisions.

### Completion gate and stop

Run five fresh-process repetitions for 1,000, 4,096, 10,000 and 20,000 simple
backgrounds in both `.glyphs` and `.glyphspackage`, plus representative complex
backgrounds at the larger sizes. Record request size, preparation, execution,
verification, cleanup, restoration, isolated peak memory and longest main-thread
work. Measure saving separately with authorized dirty fixtures. Compare the
unchanged 1,000/4,096 controls with the current implementation and larger cases
with a direct native loop; keep those different methodologies explicit.

Use an installed chat-client workflow on a disposable large font to verify full
coverage, cancellation, saved-version restoration and fresh document binding.
Oversized cases must fail clearly before execution. Investigate repeatable
regressions rather than declaring success from throughput alone.

**Stop after the capacity and correctness report. No milestone 2 work yet.**

## Milestone 2 — Make simple typed edits proportional to their scope

Implementation, 2,307 regression tests (two skips), native parity and 140 benchmark
runs pass. See the [delivery report](reports/beta8-milestone2/README.md), including
the measured small-case polling regression. Installed/editor qualification is
complete in the [joint editor report](reports/beta8-milestone3/editor-qualification.md),
including actual Save, selective recovery and native Undo/Redo.

**Use case:** color 100 glyphs in a complex family or adjust a few named glyph
widths without copying unrelated outlines or scanning every glyph twice.

**Tests first:** compare existing patch/report semantics, selected targets and
recovery. Assert that color preparation does not copy/serialize entire glyph
contents and named width requests do not enumerate unrelated glyphs. Cover
custom/indexed/absent colors, multiple masters, existing width scope, background
preservation, stale guards and native Undo/Redo. Add the existing absent-node-name
restoration reproduction: an unnamed node must not become an empty-string name.

**Changes:** use action-specific detached metadata for `set_glyph_color` and
exact lookups for named width targets. Share the necessary pure preparation
logic with retained routes. Preserve application guards, typed selective
recovery and conflict checks. Fix the demonstrated node-name restoration defect
in the existing adapter, without introducing another snapshot representation.

**Gate:** five fresh-process comparisons per file format for colors at 1/10/100
glyphs and widths at 1/100/1,000/4,096 layers. Include complex glyphs and native
apply, Undo, Redo and selective recovery. Verify unchanged controls and no hidden
worker fallback. Compare with the current native route, retaining worker results
as historical context.

**Stop after the focused performance and exact-recovery report.**

## Milestone 3 — Reduce end-of-job pauses

Implementation, 2,320 regressions, standalone native qualification and 100
benchmark runs pass. See the [cleanup delivery report](reports/beta8-milestone3/README.md),
including the reduction in cleanup pauses and increased typed edit elapsed time.
Source work continued at the user's request while milestone 2's installed gate
remained open. Both milestones now pass installed/editor qualification, including
the additional live-font inventory regression and correction.

**Use case:** a large edit finishes without a long final pause while the wrapper
closes Undo groups and restores rounding settings.

**Tests first:** exercise successful, failed and cancelled operations with many
glyphs. Check cleanup happens once, all opened groups/settings are restored, a
waiting job cannot start early, and completion is not published before cleanup
finishes. Include reconnect and native Undo/Redo after cleanup.

**Changes:** make wrapper-owned cleanup incremental using the existing scheduler
where native API ordering permits it. Keep mutation ownership through cleanup.
Measure indivisible native calls separately; do not claim they obey the chunk
budget or can be force-stopped. Do not move native objects to worker threads.

**Gate:** compare total duration and longest measured main-thread work for large
typed edits and the milestone 1 script fixtures. Verify final rounding state,
Undo history and failure recovery in the actual editor. A smaller final pause
must not come from publishing success early or abandoning cleanup.

**Stop after the responsiveness report.**

## Milestone 4 — Make polling depend on active work

Complete locally: 2,338 passing regressions (two skips), 80 final paired
benchmark runs and installed Codex Keep/blocker/reconnect checks. See the
[history-scaling and lifecycle report](reports/beta8-milestone4/README.md).
The obsolete aggregate sidecar source-line cap was removed here, bringing that
small part of consolidation (now milestone 7) forward; behavioral and package gates remain.

**Use case:** a new edit remains responsive after hundreds or thousands of
completed jobs, without repeatedly copying their full records or writing
unchanged status to disk.

**Tests first:** populate 0/100/1,000/10,000 terminal records and instrument
record reads, deep copies and writes during idle polling and one active job.
Verify unchanged polls avoid persistence, while meaningful transitions,
revisions, idempotency records and uncertain outcomes remain durable. Test
restart reconstruction, blockers, Keep and recovery reconciliation.

**Changes:** maintain the active working set using the existing registry; avoid
repeated full-history scans and unchanged writes. Reconstruct volatile indexes
on startup. Preserve historical evidence and unresolved jobs. Add no database,
history-pruning policy or persistent caching subsystem.

**Gate:** report polling latency, idle CPU, peak memory, records touched and
writes at each history size. Confirm Keep -> next task and reconnect behavior
through the installed client. Do not weaken reconciliation to improve a number.

**Stop after the history-scaling and lifecycle report.**

## Milestone 5 — Reduce conversation overhead

Complete locally, September 28: see the [delivery report](reports/beta8-milestone5/README.md).
Its implementation suite passed 2,348 tests (two skips), with 12 final focused checks;
the current card/lifecycle regressions pass 47 tests. Installed path, spacing and
kerning tasks pass on a disposable real font. User-observed Codex Details, literal
output, countdown, hidden-card and Wait checks are corroborated by server evidence.
A real sidecar disconnect/reconnect preserved the result and opt-out without replay.
The final typed test was selectively undone and the fixture saved with its original
source hash. Automated access to Codex remains blocked; the report distinguishes
user observations, transport evidence and simulated-host checks.

**Use case:** “Move these nodes, then check the result” uses the existing document
binding, one edit workflow and compact progress, with source available on demand.

**Tests first:** cover authorized edits, previews, write-only requests and save
authorization separately. Measure tool calls and response bytes. Verify cached
details cannot cross document/job/request identities; reconnects invalidate
stale bindings. Preserve equivalent text/card actions, safe text rendering and
the successful-result-only Keep timer with immediate Wait opt-out.

**Changes:** reuse valid bindings and identity-matched details; remove redundant
discovery, repeated source payloads and unnecessary status reads from routing
guidance and conversation orchestration. Keep authoritative checks at Run,
Save and Restore. Lead with intended effect and verified result; keep exact
source, technical identities and historical evidence in Details.

**Gate:** run path editing, explicit spacing and kerning tasks through the
installed client. Report call counts, response bytes and end-to-end latency
separately from native execution time. Exercise text-only operation and actual
cards, including Details, countdown, hidden/disconnected state and Wait. A card
test blocked by the environment remains explicitly incomplete.

**Stop after the installed conversation report.**

## Milestone 6 — Git checkpoints and a Git-enabled font project template

**Implemented and qualified locally, September 28, 2026.** The [qualification report](reports/beta8-milestone6/README.md) records editor, desktop and installed Codex tests, fresh-process controls, performance findings and remaining limitations. Stop here before milestone 7. The [complete implementation contract](BETA8-GIT-CHECKPOINTS.md)
preserves the supplied requirements, template directive and completion gates.
This milestone precedes consolidation; existing font projects remain unchanged
until their project setting is explicitly enabled.

**Use case:** enable checkpoints for one font project, adjust paths and spacing,
then authorize Save. Chat and the desktop app show the local revision and actual
action evidence. Later, inspect or compare that checkpoint and restore only that
font without resetting the repository or rerunning the script.

### Tests first

Write failing tests for matching/uncommitted saved baselines; clean-baseline
zero-save behavior; authorized dirty/new Save and Save As; no-effect saves;
multiple actions/manual edits; both font formats and complete package additions
and deletions; multiple fonts; unrelated staged/unstaged content; conflicts,
missing Git identity, hooks, concurrent changes and checkpoint failure after Save.
Cover duplicate/uncertain requests and restart reconciliation, bounded history,
durable action retrieval, editor-safe historical restoration with fresh bindings,
template discovery/creation and directive/config agreement. Retain typed/script
recovery, authorization and twelve-tool regressions.

### Implementation

- Add one opt-in project setting, **Create a Git checkpoint when saving through
  MCP**. It authorizes local font checkpoints, including the starting baseline;
  it does not authorize additional saves, repository initialization, unrelated
  commits or pushing. AGENTS.md documents the preference; runtime behavior reads
  the project configuration, not natural-language instructions.
- Before editing, require a checkpoint that exactly matches the verified saved
  font. Reuse a matching revision or create the saved-baseline checkpoint without
  another Save. Resolve failed/uncertain baseline creation before executing.
- After a verified MCP Save, commit only the intended font/package and its
  action record. Preserve unrelated staging/worktree content, reject ambiguous
  Git state and concurrent changes, and verify the committed font against the
  save receipt. Avoid empty commits. Reconcile checkpoint retries by existing
  save/job identity without repeating Save or execution.
- Persist small versioned action records with exact typed requests or scripts
  and parameters, full-scope references, baseline revision, execution outcome,
  actual verification and save evidence. Distinguish manual/unattributed changes.
  Preserve this evidence through Keep and bulk-artifact cleanup so a later Save
  can include several actions. Store no full chats, hidden reasoning or unbounded
  logs. Return the enclosing revision in the receipt, not inside its own record.
- Extend existing tools through negotiated capabilities for bounded on-demand
  history, action details, comparisons and restoration. Reuse desktop Git and
  font comparison components. Restore only the identified font in coordination
  with Glyphs/jobs; never replace its files behind an open document or reset the
  repository. Report whole-font/unsaved-edit coverage and the fresh binding.
  Restoring never reruns code; saving the restored result remains separately
  authorized and records a new checkpoint.
- Keep normal Keep/Save/recovery actions. Beside Save, explain its local
  checkpoint effect when enabled. Distinguish **Font saved and checkpoint
  created: <short revision>** from **Font saved; checkpoint failed**. Offer
  **Show actions**, **Compare** and **Restore this checkpoint** on demand.
- Add **Font project with Git checkpoints** through the existing template
  catalog/registry and creation flow, with README, the exact supplied AGENTS.md
  directive, font-project .gitignore, minimal configuration and action schema.
  Explain and authorize new-project Git initialization explicitly. Include no
  copyrighted font and never rewrite an existing project on selection.

### Completion gate

Qualify actual Glyphs Save and historical restoration plus an installed chat
workflow on disposable repositories in both formats. Verify staged/unrelated
content, historical commits, action evidence and existing recovery remain intact.
Measure Save-plus-checkpoint overhead on representative fonts/packages using
the shared five-run method; separate Save, Git work, verification and restoration.
Keep Git work off Glyphs' main thread wherever possible. Update canonical skills,
the packaged mirror, tool descriptions and app/template tests together.

Rebuild/install/relaunch under applicable authorization and record source, built,
installed and loaded identities. No public tool, recovery database, automatic
push, mandatory source review or implementation commit/publication is added.
Any unresolved native/client gate remains explicitly incomplete.

**Record the behavior, performance and recovery report before consolidation.
Follow the current delivery rule; stop for an unresolved gate or user decision.**

## Milestone 7 — Consolidate code and current guidance

**Use case:** an agent or maintainer finds one accurate explanation of the
twelve tools, native scripting, typed recovery and result actions.

**Tests first:** add focused assertions for current tool/capability identity,
routing examples, shared behavior and package parity. Protect v1 documentation
and local-only exclusions. Test any shared helper before removing duplicates.

**Changes:** consolidate remaining proven duplication, shorten repetitive tool
descriptions while preserving routing information, and correct stale current
guidance such as seven-tool/no-Python claims and arbitrary source-line budgets.
Clearly label historical roadmaps and link to this current plan. Preserve useful
algorithms, the development SDK/scaffolder and external analysis/export routes.
Avoid a general framework or refactor driven only by file length.

**Gate:** protocol, bridge, sidecar, conversation, routing, skill synchronization
and package checks pass. Representative task routing remains correct with the
shorter descriptions. Summarize removed branches/duplication, remaining costs
and all open native/release qualification gaps.

**Stop after the consolidation report. Begin milestone 8 only under the current delivery authorization.**

## Milestone 8 — Exact kerning edits and language-aware proofing

Restore simple pair assignments through v2's typed workflow, then improve the
read-only evidence used to choose pairs for inspection. Keep exact editing,
candidate discovery and collision analysis separate. Retain twelve public tools.

**Use cases:** set Regular/LTR `A/V` to `-72.5`; set an explicit zero exception;
remove that exception to expose inherited group kerning; apply an approved list
of glyph/group assignments in one bounded job. Separately, request a bounded
French/German proof list containing only available glyphs, with existing group
coverage and exceptions identified. A proof candidate is not a required edit.

### Tests first

- Exercise set/remove for glyph–glyph, glyph–group, group–glyph and group–group
  pairs, with exact master and `LTR`, `RTL` or `vertical` direction. Preserve
  fractions and distinguish absent pairs, explicit zero and deletion, including
  deletion that reveals inherited kerning. Do not apply LTR rules to other
  directions without native evidence.
- Cover creation, replacement, removal, already-absent removal and unchanged
  assignments; invalid glyph/group keys, masters, directions and nonfinite
  values; duplicate/conflicting entries; batch and byte boundaries. Invalid
  batches must fail before any mutation, without silently processing a prefix.
- Verify exact before/after evidence, stale guards, group/key changes after
  preparation, unrelated pairs/masters/directions, partial application failure,
  cancellation, selective Undo, Keep, Save, native Undo/Redo and reconnects.
  Include group-only pairs: today's collision-oriented native Undo owner uses
  the left glyph and cannot simply be assumed to cover group keys.
- Assert preparation is read-only and simple assignments perform no generated
  Python execution, full-font source copy or external-worker startup. Preserve
  existing saved/clean prerequisites, preview rules and separate save authority.
- Test dataset provenance/license metadata and reproducible normalization;
  language filters, unsupported languages, missing/ambiguous glyph mappings,
  deduplication, bounded work/output and deterministic continuation. Account for
  group coverage, glyph exceptions and explicit zero without labelling an
  absent explicit glyph pair as necessarily missing kerning.
- Prove discovery and proof generation neither mutate nor save the font, start
  collision analysis, nor assign suggested values. Keep dirty/unsaved read
  support. A bounded page is not evidence that the entire font was inspected.

### Exact typed editing

- Add an explicit assignment request through the existing job/conversation
  tools. Use distinct set/remove operations, explicit pair-side identities,
  master and direction; zero is a value, never a deletion sentinel. Resolve
  native glyph IDs and group keys without guessing or changing group membership.
- Reuse the existing exact kerning bridge adapter, patch representation,
  guarded application, verification and selective recovery. Extend only the
  missing request/preparation/lifecycle wiring and any demonstrated group-pair
  gaps. Prepare scalar changes from bounded native reads in existing scheduled
  chunks; preserve authoritative checks at application.
- Define and document a bounded batch within existing request/patch budgets;
  test its exact boundary. Reject conflicting duplicate pair operations and
  preserve unrelated exceptions. Do not expand group assignments into writes
  for every member glyph or introduce another recovery representation.
- Use the shared result actions: **Undo these changes**, **Keep changes without
  saving** and **Save font**. Selective Undo restores exact stored presence and
  values with conflict checks. Keep ends wrapper recovery without saving or
  clearing native Undo; failed/uncertain work retains its reconciliation rules.

### Discovery and proofing

- Replace reliance on v1's 43-pair seed for current v2 discovery with a pinned,
  documented, redistributable, language-tagged dataset. Select and verify the
  source and license before bundling; include license text, attribution, source
  revision, normalization recipe and provenance of language tags. Do not carry
  forward the seed's `commit: unknown` or invent language coverage. Preserve
  historical v1 assets and documentation.
- Filter by requested languages and glyphs actually available in the intended
  font. Document Unicode-to-glyph mapping and ambiguity handling; do not guess
  alternate glyphs or promise shaping-aware proof from a character-pair list.
  Report supported coverage and skipped/missing mappings in bounded summaries.
- Extend the existing read surface with bounded candidate/proof requests.
  Reuse native group/key and exact-pair reads to distinguish explicit entries,
  inherited group coverage and exceptions for the chosen master/direction.
  Where effective resolution is not qualified, report it as unknown. Keep
  covered pairs available for inspection; coverage is not proof of good spacing.
- Return deduplicated pairs and bounded proof strings with provenance and
  continuation/completeness information. Avoid an all-glyph Cartesian product
  or a font-wide kerning-table copy. Present **pairs to inspect**, without
  predetermined corrections or numeric values. Collision analysis stays an
  explicitly requested, separate operation.

### Completion gate and stop

On disposable `.glyphs` and `.glyphspackage` fixtures, qualify all pair-side
combinations and directions in the actual editor, including fractional values,
zero versus deletion, inherited results, selective recovery and native Undo/Redo.
Exercise installed-client preview/apply, Keep → next task, authorized Save,
stale actions and reconnects. Unverified group-pair Undo is an incomplete gate.

Benchmark 1/10/100 exact assignments and the selected batch boundary with five
fresh-process runs per format. Compare against the existing native-script
assignment workflow with matching values and scope, explicitly distinguishing
its whole-font restoration from typed selective recovery. Report preparation,
application/polling, save, verification/recovery, peak memory and longest native
chunk. Measure discovery latency, scanned candidates and response bytes across
language filters and sparse/dense glyph coverage; record installed-client
latency separately. Make no unmeasured speed or language-coverage claim.

Update the canonical kerning skill, shared kerning read/discovery/edit guidance,
tool descriptions, routing fixtures, dataset attribution and packaged mirror
when the implementation is qualified. Exact assignments should route to typed
edits; retain collision algorithms and native scripting for genuinely broader
tasks. Protocol, bridge, sidecar, conversation, routing, skill-sync, licensing
and package checks must pass. Do not advertise the planned capability early.

**Stop after the exact-edit recovery, dataset/proofing and performance report.
Release remains a separate decision.**

## Shared qualification and rollout

- Compare against a recorded pre-change source revision with matching fixtures,
  environment and timing boundaries. For timed native workloads, use five fresh
  processes per case and report median/range. Separate setup, save, preparation,
  execution/polling, verification and recovery; do not mix direct-loop timing
  with end-to-end workflow latency or call it a v1 comparison.
- Use disposable fonts. Preserve Dactylotype and unrelated documents/settings.
  Reconcile outstanding jobs before replacing a runtime. Rebuild into the
  established development target, preserve existing installation links/receipt,
  and use applicable installation/relaunch authorization. Obtain only missing
  authorization; do not make verification a reason to save unrelated work.
- Record source, built, installed and loaded identities for native delivery.
  A matching bundle on disk is not evidence that Glyphs loaded it.
- Keep canonical skills, public descriptions, routing fixtures and packaged
  mirror consistent within each affected milestone. Preserve v1 history and
  local routing exclusions; never edit installed plugin caches manually.
- Add no public tool, script mode, backup/snapshot subsystem or mandatory source
  review. Preserve useful typed algorithms, selective recovery, bounded reads
  and external export processing. Publication is outside these milestones.
- The previous benchmark and qualification evidence remains in
  [the unified-results report](reports/unified-results-20260926/README.md) and
  [the Beta 7 validation record](BETA7-VALIDATION.md). New measurements must not
  overwrite or imply completion of previously disclosed unperformed checks.
