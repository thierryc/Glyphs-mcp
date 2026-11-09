# Glyphs Health 2.6.0 / build 75 qualification

Date: 2026-11-05. Status: **unsigned local candidate; native release gates pending**.

## Delivered source and artifacts

- Shared health contract, one native resource observer per bridge, cached bridge
  and sidecar status, guarded admission and workflow waiting.
- Automatic structured/text feedback, shared skill guidance, companion health
  details, native menu summary and shared soft-budget setting (English/French).
- Verified app: `dist/local/Glyphs MCP.app`; exact source/build receipt:
  `dist/local/build-receipt.json`. See [candidate identities](candidate.json).
- Independent payloads: the full serial release gate built and recursively compared two
  payloads without differences; [gate identity](release-gate-candidate.json)
  records the resulting lean identity. Its temporary payloads were cleaned by
  the existing release runner.
- Existing uncommitted work was retained. No commit, tag, upload or feed change
  was performed. The running managed 2.5.1 installation was not replaced.

## Automated evidence

- Native desktop: **327 tests passed**, including health decoding and shared
  preference validation. Log: `build/release-test-run.dBI5eY/desktop.log`.
- Documentation: production build passed. Log: `build/release-test-run.dBI5eY/documentation.log`.
- Managed skills: 14 synchronized skills verified; lean package isolation passed
  with the unchanged 22-tool catalog and both runtime architectures.
- Packaged arm64 and x86_64 runtimes passed offline installer, HTTP catalog,
  stdio proxy, MCP App resource/CSP and text/structured-result checks. See
  [runtime evidence](health-private-runtime.json). Intel execution used Rosetta;
  this is not physical Intel Glyphs acceptance.
- Real loopback tests issue 100 concurrent status requests while native dispatch
  is blocked, require p95 below 100 ms, and assert zero native callbacks, zero
  reconciliation and zero font mutation. An independent measurement recorded
  bridge HTTP p95 **13.0 ms** and cached sidecar p95 **0.049 ms**, with four
  clients and zero native callbacks: [latency evidence](status-latency.json).
- Resource policy tests cover soft budgets, critical pressure, hysteresis,
  unavailable sources, monotonic freshness, session invalidation, newer evidence
  winning a cache race, retry identity, queue cancellation/resumption and stable
  action tokens. A one-hour virtual scheduling gap verifies that an outstanding
  observation is not duplicated or followed by a catch-up backlog.
- Ten-minute isolated observer: **0.013% of one core**, 40 bounded footprint
  samples and **zero idle native callbacks**. See [measurement](health-observer-idle-600s.json).
  This does not measure a loaded Glyphs process or prove native job regression
  below 5%. Later defensive policy-error handling did not change the measured
  idle path; loaded-artifact performance qualification remains pending.

## Final startup and connection-loss checks

Production startup now serves complete checking metadata before bridge discovery
finishes. A lost bridge connection preserves a known pressure pause until fresh
evidence or a verified new session arrives. Cached signal ages keep advancing.
The final focused health/sidecar/HTTP/queue cohort passed **69 tests**; the native
desktop suite again passed **327 tests** with the checking presentation included.
The repository’s complete serial release gate then passed on the frozen source:
**3,454 Python tests passed, three skipped; 327 desktop tests passed**.
The full Python matrix, deterministic payloads, both private runtimes, documentation,
source fingerprint and candidate validation all passed in **497 seconds**.
See [final checks](checks.json), [Python summary](python-tests.md), and
`build/health-release-gate.log`. The gate correctly reports `publishable:false`
while signing/notarization and native acceptance are pending.

## Regression-run history

An initial complete run after the main compatibility fixes passed 3,448 tests
with four skips. A later run including additional race/coalescing tests passed
3,449 tests with four skips, but one checkpoint-save test exceeded its existing
five-second wait while builds were also running. The unchanged checkpoint suite
then passed all 13 cases, and the failing case passed five independent repeats.
See [repeat results](health-checkpoint-repetition.json). Passing retries do not
establish the timeout's cause. A subsequent full run passed that checkpoint case but exposed a one-microsecond
fixture mismatch: the expiry fixture assigned three separate `time.time()` values
while asserting exact equality. The fixture now assigns one timestamp to all
three fields; the assertion is unchanged. The final full run passed **3,450 tests, four skipped**, in 289.38 seconds.
See [the complete Python summary](python-tests.md) and
`build/health-python-suite-accepted.log`. No assertion was weakened; the earlier
save timeout remains disclosed.

## Installed baseline and native gates

[Baseline status](installed-baseline.json) identified managed 2.5.1/build 74.
Its native status call timed out while an existing native script was active.
A later passive task inventory showed seven open workflows, no working tasks,
and one retained recovery offer. No Keep, Save, Undo, Restore or Close decision
was made for that work.

Pending before release promotion:

1. Resolve user-owned workflows/recovery and unsaved work, then obtain explicit
   permission for a Glyphs relaunch. The local maintenance guidance requires it.
2. Update the existing managed bridge and sidecar together, verify installed and
   loaded identities independently, and use disposable fixtures for native tests.
3. Verify zero/multiple/large/unsaved fonts, long scripts, retained recovery,
   multiple agents and companion closed; inject pressure through a bounded test
   harness with guaranteed restoration, never by exhausting the machine.
4. Measure loaded status latency and native job duration against a matching
   baseline; run the real one-hour memory/backlog soak. The virtual test is not
   a substitute for this gate.
5. Qualify clean installation and 2.5.1 upgrade, visual/localized companion
   behaviour, then prepare and verify signed/notarized artifacts. No signing or
   notarization has been attempted while native acceptance is pending.

Known architectural limit: bridge threads share Glyphs' Python runtime. A native
extension holding the GIL can delay those threads; the separate sidecar still
serves its cache and exposes stale evidence. Admission cannot police arbitrary
Python after it starts. No claim that monitoring prevents every slowdown is made.

## Handoff

The final verified local app matches the serial gate’s lean identity; its exact
source/app hashes are in `candidate.json`. Temporary payload copies created by
this task were removed after verification; final app, receipts, logs, and reports
remain. No previous distribution artifact or installed component was removed.

A fresh passive inventory before handoff still showed seven open workflows,
zero working tasks and one recovery offer available. Explicit permission was
requested for a managed update and Glyphs relaunch after the user resolves that
recovery and accounts for unsaved work. No reply has authorized a relaunch yet.

## Managed installation and native readiness — 2026-11-05

The user explicitly approved the managed update and Glyphs relaunch after
resolving recovery and unsaved work, then requested a fresh working installation.
This supersedes the earlier pending-permission note. The verified 2.6.0/build 75
payload was installed through its bundled transactional installer with native
Python preflight enabled. The companion was updated in /Applications, retaining
the previous app backup recorded in managed-app-install.json. Glyphs, the
sidecar and the companion were relaunched. The existing Codex local marketplace
plugin was refreshed through `codex plugin add glyphs-mcp@glyphs-mcp --json`;
no plugin cache was manually edited. New chats load that 2.6.0 package.

A disposable unsaved font was created through the advertised MCP tool. An
identical retry returned the original document. It was closed with the default
refuse-unsaved-changes policy; no save or discard was needed. Fresh document
discovery returned an empty list. No user font was opened, changed or saved.

See installed-native-readiness.json for loaded bridge/sidecar fingerprints,
installed app/agent identity checks, health evidence, and the bounded passive
status smoke. This establishes working native readiness, not full release
acceptance. The blocked native scheduler/pressure scenarios, representative
native job comparison, real one-hour soak, clean-install qualification, signed
upgrade, and signing/notarization remain release gates. The UI accessibility
inspection returned the Glyphs start window but took unexpectedly long; it
is not being used as health latency evidence.

## Status/health correction after installed use

The user reported status timeouts, an empty blue connection icon and unavailable
health. Live diagnostics identified and corrected a history/intake lock inversion
and starvation of cached status reads behind blocked execution workers. See
[the correction report](status-health-fix.md), installed performance measurements
and component update receipts. These supersede the earlier candidate hashes;
the earlier candidate identity is retained in candidate-initial-2.6.0-build75.json.

The corrected sidecar and companion are installed. Glyphs was not relaunched for
this correction. Native UI inspection verified green Ready checkmarks in both
Setup and the title bar and available health. Real memory-pressure warning
evidence remains visible independently of connection readiness. The full Python
suite passed 3,458 tests with 3 skips; final desktop/package results follow below.

The corrected source then passed the frozen serial gate in 477 seconds:
3,458 Python tests (3 skipped), 327 native desktop tests, documentation, packaged
arm64/x86_64 runtimes, deterministic payloads, skills/lean checks and unsigned
candidate validation. See status-health-fix-release-candidate.json and checks.json.
The earlier correction run passed every lane but was rejected by its freeze
check after qualification-report edits; it is superseded by the successful
frozen run. Final MCP status reconfirmed loaded hashes and available health.
The signed distribution and remaining full native feature gates are pending.
