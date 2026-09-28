# Beta 8 milestone 1 — native-script capacity

Status: **milestone 1 complete, with the measured limits and editor observations
below. Stopped before milestone 2.** This is local runtime qualification, not a
Beta 8 release or blanket UI responsiveness qualification.

## Delivered behavior

Native scripts no longer have a fixed 4,096-target ceiling. Explicit targets,
named selectors and `glyphs: "all"` retain exact, deduplicated coverage. The
complete internal request must still fit **4 MiB**, including source, parameters,
options, manifest and envelope. Oversize fails explicitly; no prefix is edited.
Source, parameter and output budgets remain 128 KiB, 64 KiB and 16,000 characters.
Typed-operation and read limits are unchanged.

Preparation resolves targets through the existing main-thread scheduler and
operation registry. It can be cancelled, detects document changes, does not run
Python and does not create missing layers or backgrounds. Manifest byte
accounting is incremental. Run revalidates the frozen targets in chunks, retains
the authoritative saved-baseline check and never replays Python on retries.
Twelve tools and `script.native.v1` remain; private preparation version 2 prevents
an older bridge silently handling the revised request.

## Tests first and qualification

- [Before implementation](tests-before.txt): 19 expected failures and 37 passes.
- [Final suite](final-tests.txt): **2,291 passed, 2 skipped**. The initial complete
  run exposed two stale assertions and two sandbox-denied loopback tests. The
  assertions were corrected, socket tests were rerun with permission, and the
  final complete run passed. The legacy sidecar/shared line allowance grew from
  6,600 to 6,700; per-module and total checks remain. This is not a code-size
  simplification claim.
  The skips are unavailable GitHub Copilot CLI integration and the opt-in full
  Python dependency-install matrix. No dependencies were changed; the existing
  verified bundled runtimes were reused.
- Capacity tests cover 4,096, 4,097, 10,000 and 20,000 targets; byte boundaries,
  UTF-8 and escaping; duplicate target accounting; cancellation; stale/closed
  documents; no replay; bounded compact polling; old-runtime rejection; and
  retained typed/source/parameter/output limits.
- Real native qualification passed in [.glyphs](native-capacity-glyphs.json) and
  [.glyphspackage](native-capacity-glyphspackage.json): incomplete master layers
  and absent backgrounds were not created, partial failure/cancellation stopped
  subsequent callbacks, and saved-file reload restored every fixture coordinate
  with a fresh binding. The standalone Save adapter uses the native font writer;
  it is not represented as an editor NSDocument Save.
- Installed Codex text actions completed a 10,000-background flip with one
  callback per target, assertions on every path and foreground, duplicate Run,
  optional details, actual editor saving, cancellation and restoration. Both
  file formats returned verified Save receipts and fresh restoration bindings.
  See [.glyphs evidence](installed-client-glyphs.json),
  [package evidence](installed-client-glyphspackage.json), and the
  [evidence boundaries and editor follow-up](installed-client-caveats.md).
- [Skill synchronization](skill-sync.txt) and [package checks](package-check.txt)
  pass: eleven skills, twelve tools. Canonical guidance and the packaged mirror
  describe the byte-bound capacity. Local routing and installed plugin caches
  were not changed.

## Performance methodology

All **150 measured runs passed**, five per case. Full medians, ranges, stage
timings, request bytes, memory and longest measured calls are in the
[benchmark matrix](matrix/README.md) and [machine-readable summary](matrix/summary.json).
The following are native local-workflow medians, excluding verification and
restoration, in seconds:

| Backgrounds | Contours each | `.glyphs` | `.glyphspackage` |
| ---: | ---: | ---: | ---: |
| 1,000 | 1 | 0.567 | 0.964 |
| 4,096 | 1 | 1.856 | 3.159 |
| 10,000 | 1 | 3.945 | 7.434 |
| 20,000 | 1 | 8.317 | 15.067 |
| 10,000 | 4 | 7.183 | 9.375 |
| 20,000 | 4 | 13.032 | 19.955 |

For 20,000 simple targets, the request is approximately 1.85 MB of the 4 MiB
budget. The largest multi-contour cases have median peak RSS of 846 / 861 MiB
for `.glyphs` / packages. The package reload median is 2.96 seconds and maximum
5.32 seconds; baseline validation also exceeds a second on large packages.
No callback, hashing or native reload preemption guarantee is implied.

The ten dirty 1,000-target cases each recorded exactly one Save service call:
median serialization time 0.011 seconds for `.glyphs` and 0.243 seconds for
packages. All clean candidate cases recorded zero Save calls. These standalone
font-writer timings remain separate from actual editor Save receipt evidence.

The frozen baseline matches source revision `085b5c1c` byte-for-byte for runtime
Python ([identity record](baseline-identity.json)). Both routes load identical
prebuilt disposable fixtures in fresh native processes. Fixtures are generated
outside measured processes. Five repetitions cover 1,000 / 4,096 / 10,000 /
20,000 simple backgrounds in both formats, plus 10,000 / 20,000 backgrounds with
four contours. Separate dirty cases measure prerequisite serialization.

Native timing includes local workflow preparation, callbacks, cleanup and
polling. Direct timing includes callbacks only, after target resolution and
precision/Undo setup, and excludes cleanup. They are different methodologies,
not a v1/v2 speed comparison. Peak RSS is per process and includes runtime and
fixture loading. CLI startup and installed-client latency are excluded. Simple
backgrounds have one triangular contour; multi-contour backgrounds have four
triangular contours (twelve nodes). These results do not establish a capacity or
responsiveness guarantee for arbitrary contour complexity or Python code.
Main-thread durations measure the instrumented bridge calls and scheduled
callbacks. They exclude queue waiting and native event-loop/autorelease work
outside those callbacks; they are not an OS-level UI-stall trace.

The installed observation is reported in [installed-summary.json](installed-summary.json):
about 161 seconds from the recorded applying state to the 10,000-callback result.
It included script assertions, visible editor work and concurrent regression
tests, so it is not an isolated benchmark or a measured before/after regression.
Per-tool latency is retained separately from native stage timing. Actual editor
saving is supported by receipts, not instrumentation of every NSDocument call.

The early `before-native-*` files used uncached fixture creation. They remain as
pre-change observations and are excluded from the final comparison. The separate
20,000-target probe was also exploratory, not a five-run result.

The first dirty benchmark failed before execution: its standalone Save adapter
changed the document URL from macOS `/var/...` to `/private/var/...`, invalidating
the exact prepared path. [Original evidence](failed-fixture-path/dirty-1000-1-glyphs-1.json)
and a diagnostic reproduction are preserved. A new native fixture-path assertion
failed before correcting the harness to establish a canonical URL at setup.
Only the save cases were then rerun; the 140 completed clean/direct measurements
remain unchanged. Runtime guards were not weakened and runtime source did not
change. A save that changes a document's path still requires fresh preparation.

The completed control measurements show a small total-time cost from scheduling
preparation: about 1% at 1,000 targets, 6.3% for 4,096 `.glyphs` targets and 3.0%
for 4,096 package targets. At 4,096, preparation adds approximately 150 ms while
dispatch-to-result is slightly shorter. The longest measured synchronous bridge
call before verification/restoration drops from about 188 ms to 17 ms. Callback
and cleanup stage durations remain similar. The extra preparation chunk dispatch
and exact byte accounting trade a little total time for cancellable preparation
and much shorter individual bridge calls. Restoration and baseline hashing still
contain indivisible native/file work; this is not a blanket UI responsiveness
guarantee or a claim that removing the cap makes execution faster.

## Runtime delivery

The candidate was rebuilt into `build/simple-native-scripting` and installed
through the established MCP-only transactional mechanism, reusing existing
installation/relaunch authorization. The first attempt correctly refused while
Glyphs was running; the retry succeeded after quitting the empty editor. Existing
inspectors, settings, port and runtime selection were preserved.

[Source, built, installed and loaded identities match](identity-verification.json):

| Component | Loaded code hash |
| --- | --- |
| Bridge | `318460a8e7c1d684d25dafb33643833823fc3656eb8c42435766ee270fed0375` |
| Sidecar | `4d61a1005e1439f7ccc251cd5d461b57b3a57ee1328d84152db31eb71df2909a` |

Glyphs 4.1 build 4107 loaded beta-8/build 50 with `script.native.v1` and private
preparation version 2. [Final installed status](after-installed-tests.json)
reports zero active operations. All disposable editor documents were closed;
Dactylotype and unrelated work were not opened or changed. No commit, publication
or milestone 2 work was performed.
