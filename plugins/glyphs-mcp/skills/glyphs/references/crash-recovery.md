# Glyphs crash recovery

Load only after an observed crash or unexpected exit. A timeout, a stopped bridge
or a dirty font alone does not establish a crash or justify changing autosaving.
Keep periodic autosaving enabled during ordinary work.

## Establish what happened

Stop submitting writes. Record the host bundle ID/build, process ID, crash time,
last request and job ID, loaded component identities, and relevant crash frames.
Check process existence before using UI tools that can relaunch Glyphs implicitly.
Keep evidence local; contacting developers requires the user's authorization.

Keep an uncertain write attached to its existing job ID. After an authorized
restart, refresh status and discover the exact intended document with a new ID.
Follow [connection recovery](connection-troubleshooting.md) for `interrupted` /
`bridge_operation_lost`; never replay the old patch or claim it was restored.
Do not silently substitute a font, save recovered work, or accept/discard a
recovery dialog without authority for that document and action.

A stack in Glyphs identifies the failure site, not necessarily the originating
cause. Separate native defects from possible plugin/helper contributions.
Quiet controls do not establish a fix. If the user accepts conditional
continuation, keep the normal settings and use the agreed disposable scope;
retain interrupted measurements separately. Stop the affected trial on recurrence
and report the evidence before another attempt. Do not apply this crash procedure
as a gate on unrelated offline work.

## Optional short pause — ask first

Offer a pause only when evidence makes periodic autosaving a plausible trigger.
It is an unverified diagnostic mitigation until a comparable failing control and
successful treatment support it. Permission to continue testing or install a
candidate does **not** authorize disabling autosaving. Ask for explicit approval
for this incident and experiment; do not repeat the question after approval
within that agreed scope. Declined or unanswered means no pause.

Example question:

> May I pause periodic autosaving in Glyphs 4 for one disposable-font test, for at
> most five minutes? This affects all open fonts in that app, so automatic crash
> recovery may miss changes during the pause. I'll restore the recorded setting
> when the test ends, on error/cancellation, or before the time limit. Restoration
> is manual, not automatic. No is fine; we can keep autosaving enabled and stop
> the affected test.

Before asking, identify the exact application and proposed disposable test,
resolve unrelated/unsaved documents, and give the expected benefit and limits.
Choose a shorter bound when sufficient. A longer period or another incident
needs a new explicit agreement. If you cannot remain available to restore the
setting within the bound, do not start; let the user perform a manual experiment.

## Execute only the approved experiment

Use the existing **Window → Macro Panel** in the intended Glyphs 4 application,
not an invented MCP Python tool. Read and record the native
`NSDocumentController.sharedDocumentController().autosavingDelay()` value first
(`NSDocumentController` is from `AppKit`), along with the process ID. If unavailable,
stop; do not guess a restoration value. If already zero, report that fact and do
not claim to have enabled a new pause.

After approval, `setAutosavingDelay_(0)` pauses **periodic** autosaving. Verify
the readback and record start/deadline. It affects the whole application and does
not cancel already-dispatched callbacks or prove that all save paths are disabled.
Use a fresh, explicitly authorized session when old callbacks may remain pending.
Manual saving is still possible but must be authorized for the exact document;
never save a user font merely to run a benchmark.

Restore the exact recorded delay in the same process at the first of completion,
error, cancellation or the agreed deadline; check the deadline between bounded
steps. Read back and verify restoration before resuming normal work. If the
process crashes/restarts, the old pause record belongs to the old process: verify
the new process's setting independently. Do not claim that elapsed time, a restart
or an attempted setter proves restoration. If restoration cannot be verified,
tell the user immediately and leave the affected work stopped.

Do not persist defaults, toggle Use Versions as a substitute, patch the host,
retain closed documents, add a watcher/service, or change Undo. Record the pause
separately from normal benchmark samples. Even a quiet paused trial does not
prove the crash fixed.

Sources: [Glyphs maintainer's autosave diagnostic](https://forum.glyphsapp.com/t/glyphs-3-3-3316-suddenly-crashing/31415),
[Apple periodic autosaving contract](https://developer.apple.com/documentation/appkit/nsdocumentcontroller/autosavingdelay).
The forum case is Glyphs 3; the API contract does not establish a Glyphs 4 crash fix.
