# Milestone 4 — polling depends on active work

Date: September 27, 2026. Candidate: beta 8, build 50. Source, installed-client
and performance qualification are recorded here; this is not a publication.
Status: **complete locally**, with 2,338 passing regressions, two optional skips,
80 final paired benchmark runs and installed Codex lifecycle checks.

## Changes

The existing job registry now keeps volatile status/document indexes and recent
write order. Activity reconciliation selects active jobs and copies only the
bounded recent summary. Conversation supervision visits active workflows; key,
job and document indexes replace repeated completed-history scans at dispatch.
Startup reconstructs these indexes from the existing JSON records.

An unchanged job observation returns its freshly read evidence without rewriting
the record or advancing timestamps. Meaningful progress, errors, action-token
consumption and workflow revisions still persist. An absent field differs from
an explicitly stored empty value. Failed/cancelled scripts that executed remain
unresolved; Keep, recovery and uncertain-outcome rules are unchanged.

No database, history pruning, persistent cache, new public tool or execution mode
was added. Completed history still costs startup time and resident memory. Work
still scales with the number and size of unresolved jobs; the improvement does
not make arbitrary active records constant-cost.

## Tests first and scope adjustment

`tests-before.txt` records eight expected failures and four passing controls:
whole-history copies, unchanged writes and full-history supervision. The first
collection attempt required correcting the test import order before this run.
`tests-after-initial.txt` records 90 passing focused tests.

The first full run found two errors in a newly added test that incorrectly kept
two writers open against the same registry. The restart test now performs the
transition in one store and reconstructs it afterwards. Production remains a
single-writer registry. The run also hit the reset-era aggregate sidecar line
cap by 44 lines. Its removal was brought forward from milestone 6 rather than
raising the cap or compressing code. Behavioral scaling, persistence and package
checks remain; unrelated historical size assertions are unchanged in this step.
The corrected focused run passed 25 tests.

`tests-full-final.txt` records **2,338 passed, two skipped**, with five existing
dependency deprecation warnings. Eleven-skill synchronization, twelve-tool
package checks for both architectures and `git diff --check` pass. Runtime
behavior changes in this milestone do not change the public skill contract;
the sidecar's persistence/reconnect documentation was corrected.

## Installed Codex and actual editor evidence

The candidate was built into the established target, installed through the
existing MCP-only installer and verified against the loaded identity. The
installer refused the first attempt because Glyphs was open; it made no update.
After the authorized save of the disposable dirty font, Glyphs was closed and
relaunched with all documents clean. Dactylotype was reopened unchanged and was
never saved or edited by this qualification. Existing companions, runtime, port
9680 and autostart settings were preserved.

Loaded sidecar: `4f63a0966f493d295738b5b05422204826f2bea1fd6b9a596cd922a8c4e15f22`.
Loaded bridge, unchanged in milestone 4:
`d9ad46e01f0f0a5baa93320dc6e9d887d8b4b5485f6a89950015d238d7273119`.
`build-verification.json` confirms 93 Python source files match the build and
built/installed payload identities match. Twelve tools remain advertised.

On the disposable 5,000-glyph `Cleanup.glyphspackage` in Glyphs 4.1 (4107):

- Applied +0.125 to `probe0` and opted out of automatic Keep.
- Ten unchanged reads through the installed Codex connection retained identical
  job bytes, nanosecond modification time, `updatedAt` and workflow revision.
  Those tool calls took 30–40 ms each, separately measured from registry timing.
- Requested +0.25 for `probe1`; it correctly reported the earlier workflow as
  its blocker. Restarted only the sidecar while retaining Glyphs and the edits.
- The original result returned interrupted. Its old action token was rejected;
  Check result recovered the applied outcome without replaying it.
- Keep and duplicate Keep both returned the completed original workflow. The
  waiting task retained its document binding and moved to Save and continue.
- The second workflow advanced through separately recorded explicit Save and
  Keep actions during the test. An attempted older Wait action was rejected as
  stale. This is observed action evidence, not a claim about who dispatched
  those actions or about the automatic timer. The already-kept job was not
  replayed or subjected to selective recovery.
- Fresh bounded reads verified `probe0=500.125`, `probe1=500.25`, and the untouched
  control `probe2=500`. A final authorized Save left the test font clean.

Full responses and receipts are in `installed-client.json`,
`installed-B-finished.json`, `installed-reconnect.json` and the before/after poll
records. The in-progress record is retained as chronological evidence.

## Measurement method and limits

`scripts/run_active_work_benchmarks.py` runs five fresh-process comparisons per
0/100/1,000/10,000 completed-job history, idle or with one active job: 80 final
runs. The frozen baseline is the qualified milestone 3 source, including its
editor-inventory correction, not HEAD or v1. Both routes use identical synthetic
persisted histories. Each run reconstructs the stores, measures 20 activity
reads and 100 supervisor ticks, and counts record copies, disk reads and writes.

CPU figures measure actual polling work with sleeping excluded; they are not a
whole-app idle CPU percentage. macOS peak RSS includes history creation and
startup, not just polling. The final benchmark processes run serially on the
same desktop; they are not a controlled hardware responsiveness guarantee.
Earlier exploratory runs in `pilot-matrix/` overlapped regression testing and
are excluded from the comparison. Editor execution and connector latency are
not included in this registry benchmark.

See `benchmark-table.md`, `benchmark-summary.json` and `matrix/` for medians,
ranges and each raw observation. No font-edit throughput claim follows from
these polling measurements.

At 10,000 completed records, median idle activity reads decreased from 377.381
ms to 0.069 ms; with one active job, from 368.171 ms to 0.131 ms. Each idle read
copies five recent records instead of 20,000; with active work, six instead of
20,004. Active reconciliation still performs two fresh disk reads but makes no
unchanged write. Idle supervisor work dropped from 2.640 ms/tick to about
0.0003 ms/tick. Peak process memory in this fixture decreased from 160.6 to
151.4 MiB; it still grows with retained history.

The empty-history idle case regressed from 0.0026 to 0.0052 ms (about 2.6
microseconds). This fixed overhead is disclosed; it is not evidence of an
observable editor delay. No large-history repeatable regression was measured.

## Next gate

Milestone 5's installed MCP/text checks are accessible. Its visual Codex card
gate cannot currently be driven through computer use: selecting the Codex app
returned “Computer Use is not allowed to use the app 'com.openai.codex' for
safety reasons.” No alternate UI automation was used to bypass this restriction.
Actual Details, countdown/progress, hidden/disconnected and immediate Wait
behavior remain separate, explicitly unqualified card checks.
