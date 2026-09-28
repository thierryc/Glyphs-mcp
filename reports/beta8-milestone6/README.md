# Milestone 6 — Git checkpoints and font project template

Qualified locally on September 28, 2026. The corrected MCP component and matching
desktop app are installed as **2.0.0-beta.8, build 50**. Stop here; milestone 7
has not started. No implementation commit, push or publication was made.
Milestone 5's separate visual Codex-card gate remains incomplete; this milestone
used the actual installed Codex MCP connection and the native desktop app.

## Delivered behavior

- Opt-in `.glyphs-mcp.json` policy shared by project settings and the sidecar.
  Existing projects are not enabled automatically; AGENTS.md is guidance only.
- Exact saved-font baseline before an authorized edit. A matching baseline is
  reused without another editor Save. Preparation/preview never checkpoints.
- Verified MCP Save followed by a font-only Git checkpoint with durable action
  evidence. Keep retains evidence for a later Save, without saving or extending
  wrapper recovery. Unrelated staged and working files stay untouched.
- Separate Save and Git outcomes. **Font saved; checkpoint failed** has a Git-only
  Retry. Known commit transactions reconcile without another Save or edit.
- Bounded history, action/scope retrieval and comparison through the existing
  tools. The app reuses its Git text and package-glyph comparison views.
- Historical restore loads the selected font in Glyphs, preserves repository
  history and returns a fresh binding. It replaces later unsaved edits, clears
  Undo and never saves. A later authorized Save records the restoration.
- A bundled **Font project with Git checkpoints** template, with explicit Git
  initialization, configuration, the requested agent directive, README and
  action-record schema. It contains no font and makes no initial commit itself.
- Twelve public tools remain. The extensions advertise `font.checkpoints.v1`
  and `font.checkpoint-restore.v1`; existing typed/script recovery remains intact.

## Tests and installed qualification

Tests preceded implementation, with failing evidence retained for baseline/Save
integration, history, restoration, batching, configuration and reconciliation.
The final [Python suite](python-qualified-final.txt) passes **2,404 tests**, with
three skips and five warnings. The final [desktop suite](swift-qualified-final.txt)
passes **214 tests**. [Package](package-qualified-final.txt) and
[skill synchronization](skill-sync-qualified-final.txt) checks pass: twelve tools,
eleven mirrored skills and both runtime architectures.

Real Git tests cover exact bytes, package additions/removals, unrelated staging,
multiple fonts, attributes/filters, hooks, missing identity, stale sources,
concurrent branch changes, failed publication, duplicate retries and bounded
history. Focused native-bridge tests cover partial/uncertain restoration,
ownership and explicit acknowledgment. Closed/stale-document guard behavior is
covered in bridge/service tests; no crash-survival guarantee is claimed.

Disposable real-font copies had 423 glyphs, nine masters and about 2.26 MB of
saved content (one `.glyphs` file or a 451-file `.glyphspackage`). Installed
editor qualification passed in both formats:

- Fractional width edits, Save and exact Git/source verification; untouched A
  controls and unrelated staged/working files verified.
- Intentional script failure after changing outlines, width, kerning, features,
  grid and metadata; explicit Keep, then historical restore. Native assertions
  verified 69 H/A/V/T/o/n layers, kerning by glyph name, features, metadata and
  cleared document/glyph Undo managers.
- A Git hook introduced after application caused checkpoint failure after a
  successful Save. Removing it and Retry created the checkpoint with the same
  `savedAt`, without another Save.
- Installed Codex Keep → next task → Save As → Save, with byte-identical original
  file; manual Glyphs Save → Check and continue → application → result Save.
- Duplicate Codex Save dispatch returned the same revision. Restart reconciliation
  recovered an already saved result without replay.
- App template discovery/creation, explicit initialization disclosure, settings
  opt-out/opt-in, history, action details, package-glyph visual comparison and
  historical Restore → Keep. Selection changes clear stale action details.
- First checkpoint in the template-created repository worked without a preexisting
  commit; configuration and agent directive were present.

See [file qualification](editor-glyphs-final.json),
[package qualification](editor-glyphspackage.json),
[Codex Save As](installed-codex-saveas.json),
[manual save](installed-manual-save.json),
[duplicate/action evidence](installed-codex-final.json), and
[restart reconciliation](installed-batched-runtime.json).

## Performance

These measurements answer different questions and must not be combined into a
single speedup claim. None is a v1 comparison or a fresh-editor-launch benchmark.

Actual editor Save/checkpoint tests used five repetitions per format through a
fresh FastMCP client in the same Glyphs editor process. Values are seconds,
**median [minimum–maximum]**. The post-save interval includes Git, source/index
verification and response/polling overhead; it is not isolated Git CPU time.

| Measured stage | `.glyphs` | `.glyphspackage` |
| --- | ---: | ---: |
| Preparation + application | 1.720 [1.611–1.764] | 2.109 [2.100–2.319] |
| Save + checkpoint to completed response | 1.985 [1.938–2.236] | 2.560 [2.440–2.685] |
| Dispatch to verified native Save | 0.308 [0.291–0.568] | 0.695 [0.603–0.744] |
| Verified Save to completed response | 1.669 [1.647–1.839] | 1.837 [1.796–1.971] |
| Final historical restore, including preparation/application/polling | 2.462 [2.348–2.956] | 2.879 [2.627–3.053] |
| Separately authorized Save after that restore | 2.072 [1.993–2.295] | 2.417 [2.260–2.490] |

The final restoration rows have five completed runs per format in
[restoration-batched-timings.json](restoration-batched-timings.json). Initial
per-file Git materialization took 18.546 [18.322–18.749] seconds for the four
completed package runs; the fifth exposed a cleanup race. One bounded Git batch
replaced hundreds of process launches. The final ten restore/save runs passed.

There are also **20 fresh native-process controls**, five per format with the
same candidate's checkpoint policy enabled/disabled. They use the existing
standalone GSDocument harness and its native **GSFont writer**, not actual editor
NSDocument Save. Exact stage ranges, isolated process peak RSS and longest
measured main-thread calls are in [native-summary.json](native-summary.json).

| Fresh-process metric | `.glyphs` off / on | `.glyphspackage` off / on |
| --- | ---: | ---: |
| Median preparation | 0.062 / 0.071 s | 0.100 / 0.100 s |
| Median application + baseline check | 0.235 / 1.288 s | 0.202 / 1.453 s |
| Median Save/verification/checkpoint/polling | 0.257 / 2.630 s | 0.329 / 2.566 s |
| Median native writer time within Save | 0.016 / 0.019 s | 0.111 / 0.085 s |
| Median checkpoint work after Save | <0.001 / 2.373 s | <0.001 / 2.248 s |
| Maximum isolated process peak RSS | 234.5 / 231.8 MiB | 232.1 / 231.8 MiB |
| Longest measured main-thread call | 49 / 108 ms | 259 / 151 ms |

Checkpointing adds meaningful latency; it is opt-in durability, not a speedup
for ordinary edits. Other qualification work ran on the same machine, so small
differences and maxima are not responsiveness guarantees. This on/off control
does not claim a comparison with an archived pre-change implementation.
RSS covers the isolated native benchmark process, not Git subprocesses or the
running editor's total memory.
The [native runner](run_native_matrix.py) and [benchmark](benchmark_native.py)
are retained with raw per-process evidence. The installed Codex Save-dispatch
call took 5.563 seconds in one recorded sample and returned `saving`; it is
client/tool latency, not the completed editor-save benchmark above.

## Findings fixed during qualification

- Historical result reads repeatedly replaced fresh document state with an old
  generation, making valid actions stale. Fresh bindings now update once.
- Partial/unknown historical reloads could release ownership prematurely;
  explicit acknowledgment and reconciliation now preserve the uncertainty.
- Save-phase action records understated guarded application. The recorded
  lifecycle phase remains separate from actual application verification.
- History selection could retain another revision's details; those are cleared.
- Package hashing and historical materialization launched Git once per file;
  both now use bounded batches, with restoration streamed in 1 MiB pieces.
- Concurrent completion reads could race removal of temporary directories,
  presenting a successful Save as failed. Cleanup is idempotent and failed
  presentations reconcile accepted jobs through reads without saving again.

The initial native verifier also compared load-specific kerning IDs and printed
dictionary order; it was corrected to compare glyph names and pair values.
Read-only whole-script verification marks its font dirty under the existing
script wrapper, so the harness explicitly exercises the authorized Save
continuation. Earlier failed test evidence was preserved rather than overwritten.

## Boundaries and remaining limitations

- Git is local and opt-in. No push, automatic unrelated commit, backup system or
  implicit font Save. Unsupported transforming attributes, active commit hooks,
  sparse checkout, auto-CRLF/signing settings and ambiguous Git states fail
  explicitly rather than bypassing repository policy.
- Checkpoints are bounded to 100,000 files / 512 MiB per font; action records to
  8 MiB and combined action/scope evidence to 64 MiB. History pages contain at
  most 100 entries. Text comparison is limited to 1 MiB per file; visual font
  comparison uses individual glyph files in packages. Larger whole-file text
  comparisons report the limit. These bounds do not truncate edits silently.
- Native reload/Save calls are indivisible; the app remains subject to Glyphs'
  behavior. External files/effects are outside font-only recovery. Disk-full,
  OS crash and every possible native content type were not destructively tested.
- Interrupted Git publication can require manual reconciliation, including a
  stale Git lock after a hard process crash. No persistent crash-recovery promise
  or automatic lock removal is made. Transaction staging/evidence remains in
  existing job storage; long-term storage compaction is not implemented here.
- The earlier milestone-5 visual Codex-card test remains a manual gate because
  automated access to the Codex UI is blocked. Native desktop UI and installed
  Codex tool workflows passed here; this does not certify that separate card gate.

## Rollout and preservation

Source, fresh build receipt, installed app and loaded MCP identities match.
Final sidecar: `56caaeb5922e117935ed969c216121bc7cce985af65db0ae2319736712142b91`.
Final bridge: `c35ab0983487fb32734006b1244a83d00264f0af24ae5b7395ec77653174364c`.
See [runtime installation](install-batched.txt),
[desktop installation](desktop-install-batched.json) and
[loaded identities](installed-batched-runtime.json).

Only the MCP runtime component was updated; existing companions/settings and
plugin caches were preserved. The desktop app was updated from a verified fresh
build, with prior app copies retained in ignored build directories. Dactylotype
was neither edited nor saved. Existing milestones' uncommitted work, v1 history
and local-only routing customizations were preserved.
