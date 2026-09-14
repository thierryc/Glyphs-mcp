# Glyphs MCP v2 — Simple Reset

## Decision

The current v2 is a research prototype, not the base of the next release.

Preserve it on an archive branch, then start again from stable Glyphs MCP
1.11.0 on `main` (`13ca8056`). Do not simplify the current transaction system
in place.

The new product has one goal:

> Let an agent inspect and change a font without making Glyphs feel slower.

Responsiveness wins over transparent snapshots, exact full-font
reconciliation, custom history, and support for every document state.

## Workspace implementation

The lean path is implemented independently under `src/protocol`, `src/bridge`,
and `src/sidecar`. `scripts/build_simple_v2.py` assembles a portable sidecar
and `Glyphs MCP Bridge.glyphsPlugin` without copying or importing the old v2
runtime. The initial external bulk job is `width_delta`; its result is applied
as a reversible native change and is never saved automatically.

The test-proven-benefit queue is being implemented sequentially: spacing,
refined collision kerning, start-node correspondence, then optional straight-stem
preservation after slanting. Each item needs its benefit test, native bridge
integration, deterministic build, and disposable-font responsiveness gate before
the next begins. Progress and limits are tracked in `LEAN-V2-BENEFITS.md`.

The bridge binary comes unchanged from GlyphsSDK revision
`0f5422db727b78cb42abfb386f33ae0b382b0c4d`. Automated build tests enforce the
core and per-module line budgets and deterministic bundle identities.

The bridge has one application-wide lifecycle shared by document palettes.
**Edit → Glyphs MCP Server…** opens a settings window with Start/Stop controls
for both listeners, status, the MCP URL, automatic startup at login, and logs.
A GeneralPlugin controller keeps the menu available without an open font; it
shares a bundle with the PalettePlugin through Glyphs' `Principal Classes`.
Process control runs externally. A manual Stop survives opening another font
and refuses to interrupt an active native write. The sidebar's fixed 30-point
content height fits one status row, “Ready on port 9681,” with the bridge version
in the palette title and no separate detail lines.

The September 4 milestone work found and fixed:

- Cocoa run-loop starvation between otherwise short write chunks;
- fractional-width rounding in external preparation and native Undo/Redo;
- dirty-state detection and false invalidation from clean selection changes;
- overlapping native Undo groups and unbounded bridge operation retention;
- Curve Inspector drawing the active glyph's overlay on neighboring layers;
- the missing external server at the connector's configured MCP endpoint.

A local evaluation installation now includes the external sidecar, bridge and
two optional companions. `scripts/install_simple_v2.py` verifies build identities,
backs up replacements, leaves unrelated plugins alone, and optionally starts a
user LaunchAgent for the sidecar at port 9680. The bridge remains at port 9681.
This evaluation uses the workspace Python environment with FastMCP; it is not a
self-contained release installer. The existing Codex connector URL is unchanged.

The reference display is now in scope at the user's request. It is a standalone
**Changes Against Reference** Reporter, configured through **Edit → Comparison
Reference**. Saved fonts, font files, local Git, and public GitHub revisions are
loaded outside Glyphs. Only the active layer's bounded geometry is captured in
the host; drawing consumes cached Cocoa paths. No proposal history or generic
Python execution has been reintroduced.

Qualification evidence is recorded in `build/milestone-acceptance-current.json`
and `build/milestone-acceptance.md`. The September 4 editor gate now passes on
Glyphs 4.0.1 (4004), using exactly one disposable Dactylotype document at a time.
Three consecutive 3,839-layer +8 applications preserved every fractional width;
bridge main-queue round-trip p95 was 10.46–12.87 ms and maximum 49.53 ms, including
two seconds of sampling after each operation. Cancellation after 150 changes
restored all targets exactly. Native Save persisted all 3,839 accepted widths,
confirmed by reloading the file in an external native process. The original
Dactylotype source remains byte-identical; intentionally saved disposable copies
have their own recorded hashes.

The editor gate exposed a flaw missed by the isolated native-process test:
Glyphs routes Edit-view Undo to each glyph's own history. Exact inverses now use
those native managers, with weak references to avoid retaining their owner.
Native Undo and Redo restore the active glyph's layers exactly while preserving
other glyphs; native Revert and `discard_job` restore the whole font/job. The
final editor Undo/Redo round trips stayed below 157 ms. Whole-job discard passed
twice with exact read-back of every target.

RSS after the three bulk runs was 414.9, 487.2 and 470.4 MiB. Closing the second
font released about 99 MiB of native editing history. The runs contained different native-history states, so this does not prove a
zero retained-memory slope. All-day memory qualification remains release work. The bridge retains at most eight
completed operation records; native histories remain owned by Glyphs.

Saved, font-file, local Git and public GitHub references passed manual editor
checks, including Save refresh, active-layer switching, a missing glyph and an
unmatched special layer. File and public GitHub comparison, and Curve Inspector drawing, also worked
with the external MCP server stopped. The public SDK reference was pinned to commit
`1c5a8639ba643dfd9d6379b8daad4173b67aab73`; lowercase a exercised visible outline
and width differences. Neither local fonts nor font data were uploaded.

The seven-tool Codex connector now also survives sidecar replacement: HTTP is
stateless, while job state remains in the service. A regression check sends an
old session ID without reinitializing; the actual Codex connector was verified
after restart. The full Python suite passes with 1,974 passed and 5 skipped;
deterministic builds, line budgets and `git diff --check` pass.

The September 5 server settings update is installed and visually verified in
Glyphs, including the menu with no font open and native Start/Stop. Its redesigned
dialog uses quiet status polling, preserves typed input, and adds an editable
MCP port with Copy URL. A live 9680 → 9790 → 9680 round trip passed, with an actual
MCP read on 9790; native Stop closed both listeners. Automatic-start persistence,
invalid/in-use port checks, rollback, and reinstall preservation are covered.
The footer credits Thierry Charbonnel, links to GitHub and sponsorship, and
shows Version 2.0.0 (Bridge 0.1.0). The server was left running on 9680 with its
original automatic-start preference enabled.

The experimental runtime remains recoverable in this dirty research worktree
and is excluded from the lean build. Archiving and starting from the stable
branch must preserve this uncommitted evidence. Nothing is published.

## Architecture at a glance

```text
Codex / MCP client
        |
        v
Standalone MCP sidecar
  jobs, files, glyphs-cli, knowledge
        |
        | small local protocol
        v
Glyphs MCP Bridge
  bounded reads and short writes
        |
        +---- optional independent companions
                Curve Inspector
                Changes Against Reference

Existing external plug-ins such as Icon Grid remain independent.
```

The MCP server runs outside Glyphs. The Glyphs bundle is a small bridge, not a
font database, transaction engine, or background job runner.

## Ten rules

1. No ordinary live call traverses, hashes, diffs, canonicalizes, or serializes
   a complete font.
2. No main-thread callback intentionally processes a complete font.
3. Expensive work runs outside Glyphs against a saved source copy.
4. Bulk work requires a saved, clean document. The human saves dirty or
   pathless documents first.
5. The plug-in never saves automatically.
6. Save means accept. Native Undo restores each glyph; Revert or
   `discard_job` restores the whole font/job.
7. Review is non-modal; the user can inspect and edit normally.
8. Safety checks cover the source and explicit targets, not a second complete
   font model.
9. Cancellation stops future chunks. It does not start an internal recovery
   framework.
10. A real Dactylotype test is required at every milestone.

## The user workflow

```text
Open a saved font
        |
        v
Ask the agent for a change
        |
        v
Keep working while the change is prepared
        |
        v
Review the reversible change in Glyphs
        |
        +-> Save: accept
        +-> Undo: restore the active glyph
        +-> Revert / discard_job: discard the whole font/job
```

There is one user decision: keep the visible change by saving, or discard it
with native per-glyph Undo or whole-font Revert. The agent can also discard the
whole job. There is no separate approval before application.

For a large job, the agent asks the user to save first if the font is new or
dirty. Copying, hashing, external computation, validation, and chunked
application are implementation details and stay outside the user workflow.

There is no automatic `makeCopy` for a dirty document and no three-way merge
with a changing live font.

Small edits may skip `glyphs-cli`. The bridge remembers old values for only the
explicit targets, groups changes in each touched glyph's native Undo manager,
and reads those targets back.

## Three components

### 1. Standalone sidecar

The sidecar owns:

- MCP networking and authentication;
- saved-source copying and hashing;
- `glyphs-cli` processes;
- job progress, cancellation and temporary files;
- compact patch generation;
- packaged skills, knowledge and logs.

Job storage is a normal temporary directory containing small JSON and source
artifacts. Do not introduce a database or content-addressed object store.

### 2. Glyphs MCP Bridge

The bridge owns only:

- connection and runtime status;
- open document, path, dirty state and selection;
- bounded reads for explicit objects and fields;
- time-sliced patch application;
- target-level read-back;
- native Undo and progress.

Its fixed-height sidebar panel shows only availability, version, port, and an
optional startup error. It contains no request activity, companion list,
metadata editor, curve UI, font model, custom history, or proposal Reporter.

All Glyphs object access stays on the main thread, in callbacks targeted at
8–12 ms. The bridge yields between chunks and never keeps UI updates disabled
across callbacks.

### 3. Independent companions

Companions are separate Glyphs bundles in the same repository. Each must work
manually without Glyphs MCP. When the bridge is present, a companion may
register a tiny capability manifest.

Registration is idempotent so load order does not matter. A broken companion
must never prevent the bridge from starting.

#### Curve Inspector

Create `Glyphs Curve Inspector.glyphsReporter`.

- Keep UI and drawing in the companion.
- Put mathematics in a small pure-Python `curve_core` package.
- Reuse `curve_core` from external jobs.
- Keep Reporter callbacks drawing-only.
- Match the proven teal/pink curvature teeth and connected envelope display.

#### Changes Against Reference

Create `Glyphs Reference Inspector.glyphsReporter` independently of MCP.

- Select Last Saved, a saved font file, local Git, or a public GitHub revision.
- Refresh native checkmarks, selected filenames/revisions, and full-detail
  tooltips when Comparison Reference opens. Keep chooser actions editable and
  clear unavailable selections for no font or an unsaved font, without polling.
- Pin a private reference snapshot across glyph switches; refresh explicitly or
  after a native Save when Last Saved is selected.
- Compare the active layer's outlines (including components and open paths),
  anchors, and width. Match layers by ID, with unique master-name fallback for
  master layers only; report missing special layers instead of guessing.
- Load fonts and resolve Git outside Glyphs; bound geometry and reference caches.
- Paint cached mint reference geometry, cyan current geometry and metric changes.
- Keep completed paths visible during edits; capture after a 150 ms quiet period
  with no mouse button held. Coalesce pending updates, reject obsolete results,
  and stop the deferred callback when idle. Clear paths on context changes only.
- Work manually without the bridge; register only a capability manifest with it.

#### Icon Grid

Do not duplicate Icon Grid inside v2. The existing standalone
`IconGrid.glyphsReporter` remains the single implementation and release. If it
later opts into MCP discovery, it may publish the same tiny capability manifest
through the shared registration helper. It does not add a dedicated MCP tool
or become a bridge dependency.

## Small public surface

Begin with seven MCP tools:

1. `get_status`
2. `list_documents`
3. `read_entities`
4. `start_job`
5. `get_job`
6. `apply_job`
7. `discard_job`

Bulk results remain on disk. MCP responses contain a job ID, counts, hashes,
warnings and a small sample—not thousands of changes.

Knowledge belongs in sidecar resources and agent skills. It is not advertised
through the live Glyphs bridge.

## Small formats

Use ordinary versioned JSON, handwritten once.

Compact patch:

```json
{
  "version": 1,
  "jobId": "job_123",
  "documentId": "doc_456",
  "sourceHash": "sha256:...",
  "changes": [
    {
      "kind": "set",
      "glyph": "A",
      "layer": "MASTER_ID",
      "field": "width",
      "before": 600,
      "after": 608
    }
  ]
}
```

Companion manifest:

```json
{
  "protocol": 1,
  "id": "curve-inspector",
  "version": "1.0.0",
  "capabilities": ["curve.measure", "curve.overlay"]
}
```

Initial patch kinds are `set` and `translate`. Add another only when a proven
workflow cannot use them. Do not build a general remote-object protocol.

## Safety without a complete font model

For bulk work, retain only:

- document ID, path and dirty state;
- saved-source SHA-256 and backup;
- bridge edit generation;
- stable target IDs;
- old and new values for changed targets;
- native Undo.

Before applying, refuse and recompute if the path or source hash changed, the
document became dirty, the generation changed unexpectedly, or any target no
longer has its recorded old value.

Do not rebuild:

- complete canonical fingerprints or font trees;
- exact source-parser/native-model equivalence;
- save epochs and persistence reconciliation;
- Git-like action history and reapply;
- full-font inverse models and recovery checkpoints;
- proposal expiry, disk shards, or a proposal-history Reporter.

## What we can salvage

Port selectively:

- the separate `glyphs-cli` launcher;
- safe external source copying and hashing;
- deterministic disposable fixtures;
- stable target IDs and scalar read-back;
- pure curve, spacing and font algorithms;
- useful skills and pinned Glyphs knowledge;
- runtime identity and independent-bundle installer support.

Do not port a module merely because it has tests.

## Repository shape

```text
src/
  sidecar/
  bridge/
  companions/
    curve-inspector/
    reference-inspector/
  protocol/
tests/
  sidecar/
  bridge/
  companions/
  live-glyphs/
installer/
```

One repository avoids duplicated CI, fixtures, signing and protocol releases.
Use separate repositories only if ownership or release cadence truly diverges.

## Code-size limits

- Handwritten v2 core, excluding companions: at most 6,000 lines.
- Glyphs bridge: at most 1,500 lines.
- Sidecar core: at most 3,500 lines.
- Shared protocol: at most 300 lines.
- No handwritten module above 500 lines without explicit review.
- Generated files do not count only when they are not imported into Glyphs.

Track these limits in CI. They are maintainability constraints, not code golf.

## Reset milestones

### Milestone 0 — Archive and measure

- Preserve current `lit/v2` work on a research branch.
- Record the Dactylotype freeze, normalization mismatch and misleading test
  coverage.
- Mark the current candidate unqualified and stop release work.
- Record current handwritten lines and discovery payload size.

Exit: the experiment is recoverable; the new branch contains none of its
runtime.

### Milestone 1 — Sidecar and protocol

- Branch from `main` at `13ca8056`.
- Define the seven tools, compact patch and companion manifest.
- Start the MCP server outside Glyphs.
- Use plain temporary files for jobs, cancellation and cleanup.

Exit: the sidecar works without Glyphs and meets its line budget.

### Milestone 2 — Read-only bridge

- Build the bridge and minimal status panel.
- Add document listing, selection summary and bounded reads.
- Add idempotent companion registration.
- Add no writes, previews, Reporter integration, or Python execution.

Exit: repeated Dactylotype inspection causes no visible pause or retained-memory
slope.

### Milestone 3 — Bounded writes

- Add `set` and `translate` for explicit targets.
- Apply in 8–12 ms chunks with progress and cancellation.
- Use native Undo and target-level old-value checks.
- Never save automatically.

Exit: change and undo 10, 100 and 1,000 Dactylotype layer widths responsively.

### Milestone 4 — External bulk jobs

- Require a saved, clean source.
- Copy and hash it outside Glyphs.
- Run calculation or native preparation through `glyphs-cli`.
- Produce one compact patch and readable summary.
- Refuse stale source, generation, dirty-state, or target values.

Exit: add 8 units to every Dactylotype layer width, review non-modally, apply
in chunks, then prove Save acceptance and native discard on separate copies.

### Milestone 5 — Extract companions

- Extract Curve Inspector and `curve_core`.
- Add the independent Changes Against Reference companion and external reader.
- Remove the experimental Metadata Inspector rather than carrying it forward.
- Remove LitSquare, metadata and curve UI from the bridge.
- Keep the existing standalone Icon Grid independent; add only optional
  manifest registration in its own repository if that becomes useful.

Exit: every companion works with and without MCP; companion failure is
isolated.

### Milestone 6 — Package the proven core

- Leave obsolete v2 runtime and generated contracts out of the new branch.
- Build deterministic sidecar, bridge and optional companion bundles.
- Test independent install, replacement, rollback and unrelated files.
- Keep Glyphs 3 pinned to 1.11.0.

Exit: the visible Dactylotype gate passes three consecutive times, line budgets
pass, and nothing is published.

## Gate order

At every milestone, test in this order:

1. Visible responsiveness on a disposable Dactylotype copy.
2. Source and backup preservation.
3. Cancellation and native Undo/Revert.
4. Main-thread timing and retained memory.
5. Real bridge integration.
6. Unit tests.
7. Packaging and installer tests.

Record unloaded and loaded HTTP probe timings separately. The 200 ms probe
threshold is diagnostic, not an automatic release rejection: a round trip also
includes scheduling, transport, and modal waiting. Investigate reproducible
native-execution stalls attributable to the plugin and inspect retained memory
across repeated runs. Passing unit tests never overrides a failed visible gate.

### Shared correctness fixes (September 5)

Main-thread dispatch synchronizes pending, running, completed, and cancelled
callbacks. A pending timeout prevents later execution; a running timeout reports
an uncertain outcome with the existing job ID. The sidecar retains that operation
for status reconciliation instead of submitting another job.

Apply and discard share document ownership, reserved before native Undo begins.
Duplicates return the existing operation; rejected competitors cannot alter
native scopes or caches. Terminal and failed-start paths release ownership.

Each target records its exact starting state before a setter runs. Patch values
cover scalar, kerning, and coordinate changes; native translation and contour
reordering retain only the affected target values. A partially failing target
is restored and verified before yielding. Earlier writes use the existing
chunked rollback, with conflict guards and explicit incomplete-recovery errors.

The native history helper stores grouped values as well as scalars. Undo, Redo,
and recovery use the same exact writer, preserving native object identity and
per-glyph groups. Rounding flags and Undo registration are restored in finally;
history blocks hold Undo managers weakly.

Translation writes only foreground node, anchor, and component positions through
that exact writer; it never invokes a whole-layer transform that also moves
background images or guides. Component linear matrices stay intact. Spacing
preserves mixed assemblies with an effectively aligned component, including
layers whose aggregate `isAligned` value is false. It checks native effective
alignment, so configured mode alone does not exclude an editable mixed outline. A position that cannot retain
the requested fraction is reported during preparation, without rounding it away.
The native regression is `scripts/qualify_simple_v2_translation_native.py`.

Preparation cancellation and ready publication share the service lock and
recheck current state inside it. Abandoned artifacts are released after the
worker returns; the terminal record remains available. The seven-tool contract,
companion redraw behavior, window design, and 1,600-line bridge budget remain.

Qualification passed with 2,121 tests and five skips, deterministic builds, and
native grouped-coordinate Undo/Redo across three masters. The installed bundles
passed three 729-layer italic cycles, all 3,839 fractional-width changes,
cancellation/recovery, native master replacement, and companion reopen/node-edit
redraw checks. The saved disposable data matches an untouched native-save control
apart from editor layout state; the original source hash is unchanged. Baseline
HTTP p95 was 9.463 ms, loaded p95 stayed at or below 26.345 ms, and loaded maximum
was 113.534 ms. Two native-menu probe timeouts are recorded separately from native
execution. Full evidence and limits are in
[`build/deep-smoke/fixes-review.md`](build/deep-smoke/fixes-review.md).

## First-release non-goals

- Bulk work on dirty or pathless documents.
- Full-font immutable preview inside the current document.
- Complete canonical fingerprints or exact cross-process equivalence.
- Three-way merge or concurrent-edit reconciliation.
- Custom history, reapply, recovery UI, or proposal Reporter.
- Generic live Python with automatic full recovery.
- Structural font surgery or metadata editing.
- Signing or publication before visible acceptance.

## Success

V2 succeeds when a designer can leave it enabled all day, start a large spacing
job, continue using Glyphs while it runs, inspect the result, save to accept or
use native Glyphs commands to discard, and understand the implementation
without reading a transaction framework.

## Milestone 6 — local packaging candidate

The archived research workspace remains untouched. The candidate is assembled
from the stable 1.11.0 baseline with the lean protocol, bridge, sidecar and two
independent companions. Project version is 2.0.0, installer build 29; the bridge
version remains (0.1.0).

A shared 0.001 font-unit absolute tolerance is used only for spacing preparation
and reference comparison. Negligible translation and width differences are
assessed independently. Native writes, rollback, history and topology stay exact.
Private CPython and locked glyphs-cli/FastMCP dependencies cover both Mac
architectures. The installer stages and verifies component replacements and
restores managed files, launch agents and receipts together on failure.

Choose → Install → Ready replaces the overlapping setup flows. Fresh installs
select all three components; upgrades preserve selections and require explicit
removal. Companion-only installs are supported. Existing ports, preferences,
authentication and customized client configuration remain intact.

The welcome window is deliberately a placeholder. Its text, links and layout
are separate from its event-driven, application-wide lifetime. It presents once
after native readiness, marks its preference only after display, and reopens via
the fixed-height panel's native heart.circle button.

The local acceptance report records automated checks and the separate visible
Glyphs gate. Public signing, notarization, publication and final welcome design
are separate work.
