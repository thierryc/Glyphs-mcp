# Unified results and faster typed edits — installed; card qualification pending

Implemented typed Keep, shared successful-result card countdowns, persistent opt-out,
fresh save-status wording, and native preparation for widths, Dimensions, glyph
colors and coordinate-only node updates. Existing typed patches, selective recovery,
algorithms and external export processing remain in use; twelve public tools.
Keep releases native recovery and temporary preparation files through existing
terminal-job cleanup; durable request, summary and bounded result evidence remain.

The candidate is built at `build/simple-native-scripting` and **installed** from
commit `d75404ec`. On September 27 the user closed Dactylotype, after which the
MCP component was updated and Glyphs relaunched. Source, build, installed and
loaded fingerprints agree. Actual editor and installed Codex text checks pass
as detailed in [the installation report](installed-20260927/README.md).
Visible-card qualification remains blocked by Computer Use’s Codex access restriction.
No original font was saved, closed or changed by these qualification scripts.

## Verification evidence

- Final full suite before commit: **2,261 passed, 2 skipped**, including the two
  localhost tests; five dependency warnings. [Full run](precommit-regression.log).
- Earlier broad/focused run logs remain recorded as historical evidence.
- Subsequent focused suites: 153 passed, 50 passed after fresh typed save-status wording, 39 package/routing/native-preparation tests, and 31 Keep-cleanup/reconciliation/capability-failure tests. These runs overlap and are not an additive test count. The actual card JavaScript timer tests pass for typed and script results, including rejected Wait and unknown automatic outcomes.
- Native smoke tests: widths, glyph colors, coordinate-only backgrounds and
  100 Dimensions fields; real `.glyphs` / `.glyphspackage` fixtures, no worker
  launch or source copy on native preparation, selective recovery and native
  Undo/Redo after Keep.
- Exact worker/native patches and reports match on both formats. Named-node
  fixtures also pass targeted application and selective recovery with untouched
  glyphs, masters, foreground/background, components, anchors and metadata;
  missing backgrounds fail without creation.
- Nine-master native outline qualification passes, including partial rollback,
  cancellation, topology operations, save/reopen, node/hint identities and controls.
- The complete 320-run paired benchmark matrix passes; see [run ledger](benchmark-progress.json).
- Skill synchronization and package checks pass: 11 skills, twelve public tools,
  arm64 and x86_64 payloads. Source and built package files match.

## Performance evidence

The complete matrix contains **320 successful fresh native processes**, five repetitions for each task/size/format/route. The retained worker control and optimized native route use the same shared algorithms. All 32 paired groups show lower median preparation and preparation-plus-application time on the native route.

Selected `.glyphs` preparation + application/polling times, in seconds; each cell is median [minimum–maximum]. Saving is zero here because the fixtures start saved and clean. Verification, selective recovery, memory and the full `.glyphspackage` results are in [the complete benchmark tables](BENCHMARKS.md) and [machine-readable summary](benchmark-summary.json).

| Task | Targets | Contours | Worker | Native | Median speedup |
|---|---:|---:|---:|---:|---:|
| width | 1000 | 1 | 1.661 [1.614–1.675] | 0.577 [0.566–0.650] | 2.88× |
| width | 4096 | 1 | 3.152 [3.079–3.234] | 2.211 [2.097–2.290] | 1.43× |
| dimensions | 100 | 1 | 1.347 [1.342–1.361] | 0.312 [0.304–0.317] | 4.32× |
| color | 100 | 1 | 5.183 [4.916–5.693] | 4.395 [4.353–4.663] | 1.18× |
| outline | 100 | 1 | 1.601 [1.349–1.642] | 0.352 [0.345–0.586] | 4.55× |
| outline | 100 | 12 | 2.166 [2.151–2.444] | 1.395 [1.137–1.407] | 1.55× |

Across native runs, the longest measured scheduled coordinator chunk was **0.984 s**; the longest measured preparation chunk was **0.033 s**. Existing application/Undo cleanup is still a responsiveness bottleneck. The nominal time budget cannot interrupt a single native call or a cleanup loop.

Every measured native preparation asserted **zero source copies and zero worker launches**. Each process also checked selective recovery and a second edit followed by Keep and native Undo/Redo. The second edit/Keep qualification, fixture setup and CLI startup are outside the timed preparation/application interval.

These are local fixture measurements made before the candidate was committed, not a v1 comparison or an installed-client latency distribution. The final source/build identities are recorded separately. Result wording, retained-artifact cleanup and validation outside benchmark requests were refined during the matrix; measured preparation algorithms were kept stable for these requests. CPU load was not isolated. Worker-child and parent peak RSS are reported separately, not summed as simultaneous memory. See the full methodology before comparing these numbers with direct native loops.

## Findings and limits

Glyphs' normal layer iterator can create missing master layers. Native preparation
now uses stored objects; retained external outline preparation keeps its disposable
font behavior. A width-name regression found by the full suite was corrected:
missing explicit names are rejected before layer inspection.

All 18 retained closed native-action qualifications pass. Its feature-block hash
comparison needed the test helper to pass the selected block, rather than hash
the whole font. The known native node-name normalization also reproduced during selective
restoration on the retained worker route: absent names become empty strings.
It remains a separate follow-up; [exact evidence](known-unnamed-node-normalization.json)
is retained. The extended parity fixtures use explicitly named nodes and verify
their preservation without ignoring metadata differences.

Benchmarks measure native fixture workflows, not installed chat-client latency.
Fixture saving uses GSFont serialization; subsequent actual editor saving and
restoration passed the checks in the installation report. Installed cards remain
an incomplete gate. Native application/cleanup can still
produce a long main-thread chunk; time slicing is not a hard responsiveness guarantee.

## Candidate and rollout

[Source/build comparisons](identity-files.json) and [candidate identities](candidate-identities.json)
record the prepared payload. [Runtime preflight](runtime-preflight.json) records
the previous installed/loaded runtime and the unrelated dirty Dactylotype document.
The candidate is now installed; both inspector companions and installation settings
are preserved. The [September 27 report](installed-20260927/README.md) records
actual editor saving, Save As/manual continuation, selective Undo, native Undo/Redo
after Keep, whole-font script restoration, fresh bindings, duplicate actions,
Keep-to-next behavior, partial failure, reconnect reconciliation and individual
installed-client latency observations.

Visible installed-card countdown/Wait/Details qualification remains blocked by
Computer Use's Codex access restriction. Live fault/edge cases not repeated on
this exact loaded identity are listed explicitly in that report. Mock-host and
prior-candidate evidence do not close those gates.

Implementation commit: `d75404ec`. Publication remains excluded. Installation
and this documented editor/text pass are complete; the broader milestone retains
its explicit unqualified gates.
