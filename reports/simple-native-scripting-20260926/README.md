# Simple native scripting — qualification and performance

The [follow-up review](REVIEW.md) reproduced workflow handoff, target eligibility,
details-cache and polling issues after the qualification run. Those findings are
not fixed yet; the passing test counts below do not imply their absence.

The candidate has one script capability, `script.native.v1`, using the existing
conversation/job lifecycle. Original task authorization permits Run without a
mandatory source review. Clean saved fonts skip Save; dirty fonts use the existing
verified save action. Whole-font saved-version reload is the script recovery path.
Typed algorithms and their snapshots, patches and Undo remain intact.

Removed the arbitrary-script worker route, layer-state codec, complete-content
patches, staged transfer, snapshot preflight and script snapshot Undo. Old request
fields fail explicitly. The twelve tools remain, with optional
`get_edit_workflow(include_review=true)` for source, parameters and execution details.

## Performance

Five fresh processes per fixture and mode: 25 native workflow runs and 25 direct
callback runs. Modes run separately and sequentially. Native totals include syntax/
target preparation, an authorized verified prerequisite save, native execution and
completion polling. Direct times measure only callbacks, excluding setup/cleanup.
The fixture uses the real GSFont writer; normal editor NSDocument saving is a
separate integration gate. CLI startup, HTTP/model latency and visual frame rate
are excluded. No claim of a universal 10 ms response bound is made.

| Backgrounds | Contours each | Direct median (range), s | Native workflow median (range), s | Previous native run, s | Native peak RSS median, MiB | Longest scheduled execution chunk, ms |
| ---: | ---: | --- | --- | ---: | ---: | ---: |
| 100 | 1 | 0.009 (0.009–0.010) | 0.577 (0.571–0.588) | 0.591 | 167.6 | 8.04 |
| 1,000 | 1 | 0.097 (0.096–0.146) | 0.843 (0.834–0.850) | 0.970 | 191.2 | 10.13 |
| 4,096 | 1 | 0.386 (0.378–0.413) | 1.681 (1.626–1.899) | 2.653 | 321.7 | 19.32 |
| 100 | 12 | 0.100 (0.097–0.101) | 0.576 (0.571–0.588) | 0.593 | 171.1 | 11.18 |
| 500 | 12 | 0.515 (0.508–0.515) | 1.109 (1.102–1.111) | 1.161 | 197.9 | 11.38 |

Previous native figures are single runs from the earlier save-first report, not
five-run medians. The 4,096-background median fell from that run's 2.653 s to
1.681 s (about 37%); this is a descriptive comparison, not a controlled estimate.
The previous largest scheduled chunk was 770.5 ms; all five new largest-fixture
runs stayed below 19.32 ms for scheduled execution chunks. Synchronous review,
save and reload calls are not included in that chunk measure. A long user callback
or whole script can still block the editor.

Current RSS is isolated per mode and sampled before restoration, including fixture
and Glyphs runtime memory. The earlier mixed-mode RSS is not a comparable
save-first memory baseline. No increase to the 4,096-surface limit is justified or
made. There is no route-selection count threshold because only one script route
remains.

## Stage timings

Medians below are seconds. Save is included in dispatch-to-result; restoration
is excluded from native total. Full median/min/max figures, process RSS ranges
and measured source hashes are in `benchmarks/summary.json` and per-run JSON.

| Backgrounds | Contours | Preparation | Save | Dispatch to result | Scheduled native work | Restore |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 100 | 1 | 0.3110 | 0.0546 | 0.2669 | 0.0184 | 0.0098 |
| 1,000 | 1 | 0.3128 | 0.0580 | 0.5297 | 0.1602 | 0.0270 |
| 4,096 | 1 | 0.3204 | 0.0495 | 1.3578 | 0.6824 | 0.0703 |
| 100 | 12 | 0.3166 | 0.0385 | 0.2640 | 0.1096 | 0.0077 |
| 500 | 12 | 0.3125 | 0.0416 | 0.7990 | 0.5426 | 0.0194 |

The benchmark preceded presentation-only changes: terminal script progress now
retains callback counts (whole scripts have no count), script results no longer
advertise typed-job Undo, and an idempotent start response no longer repeats the
execution warning. The execution engine,
batching, cleanup and saving code were unchanged. Raw results retain the exact
measured hashes; the candidate manifest records the separately qualified build.

## Qualification status

- Built `.glyphs` fixture: 30 native checks passed, including controls, anchors,
  components, foregrounds, another master, fractional coordinates, partial failure,
  cancellation, whole-script metadata/features/kerning, reload and fresh binding.
- Built `.glyphspackage` fixture: the same 30 native checks passed.
- Final full regression: 2,208 passed, two skipped, with the two localhost socket
  tests deselected in the sandbox and passing separately. The earlier
  documentation-signature mismatch was corrected before this clean run.
- Additional script/UI tests: 45 passed, including script Save As non-overwrite
  and manual-save revalidation; the two localhost socket tests passed separately.
- Installed editor/client gates: pending installation/relaunch authorization.
- Package: 12 tools, 11 skills, arm64 and x86_64 runtime provenance checked.
- No publication or installed runtime changes performed.

The installed copied Beta7 runtime observed during this task advertises no script
capability. Its loaded identities were bridge `521e2506920a…`, sidecar
`44cd3cdfaac8…`; neither matches this candidate. Actual editor saving/restoration
and an installed chat-client workflow must pass before the milestone is complete.
