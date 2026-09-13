# Install, verify and iterate in Glyphs 4

Reuse installation/testing authorisation in the user's task. Resolve a restart
that would lose unrelated unsaved work before proceeding. Use fresh disposable
fonts; read-only Reporter tests need no Save.

Continue from the last verified revision. Compare workspace bytes, installed
bytes and loaded behavior when that evidence is missing or a revision changed;
retain the result for this iteration. Choose the next action from the evidence:

| Current evidence | Next action |
|---|---|
| Only documentation/report changed; plugin bytes unchanged | No plugin installation or relaunch |
| Requested artifact already installed and its loaded revision verified | Run only the newly needed native check |
| Artifact missing or installed bytes differ | Validate the completed revision, install once into the intended app, then inspect the outcome |
| Installed bytes match but the old revision remains loaded | Relaunch safely within scope, then verify loaded behavior; no reinstall |
| Install outcome or loaded revision unknown | Inspect the target path, pending prompt and native diagnostics; do not repeat Open/install while the first attempt is unresolved |

The steps below describe those phases; they are not mandatory repeated actions
for every follow-up. Batch related source edits into a testable revision. A
failed native check is a reason to diagnose that check, not reinstall identical
files. A second installer run is not needed to verify an unchanged payload:
compare the installed files/receipt and loaded evidence instead.

1. Validate the workspace artifact and record bundle identifier, principal
   class, version and file fingerprint. Keep the previous working revision.
2. Identify the intended application by `com.GeorgSeifert.Glyphs4`, since hosts
   can share a display name. Use the documented native route: open/drop the
   plugin into that specific app. Inspect the resulting Plugins location;
   do not assume Glyphs 3's folder. The offline Plug-ins handbook explains
   installation and native prompts.
   In the qualified 4.1 (4107) trial, Start Window covered an Install Plugin
   alert and the bridge timed out while that modal waited. If an open request
   appears stalled, close only Start Window and inspect the pending prompt
   before repeating the request; repeated opens can queue duplicate dialogs.
3. Plugins load at application launch. When the desired revision is not loaded,
   relaunch within authorised scope with
   unrelated documents safe; do not promise hot reload. Check installed bytes
   against the artifact, then verify the expected class/menu/version behavior
   in the running Glyphs 4. A file hash alone is not loaded-code evidence.
4. Open the disposable fixture and activate the native plugin menu. Inspect
   actual output and native diagnostics. In Glyphs 4.1 (4107), use **Window →
   Floating Macro Console** or **Window → Scripting Window**; inspect the native
   menu on another build rather than assuming Glyphs 3 menu locations.
   On failure record traceback, class, installed path and host build. An
   authorised helper may provide bounded independent proof; it must not
   silently implement the plugin's missing behavior.
5. Verify behavior and preservation: empty/mixed selections, active layer/master,
   Font View, dirty state, zoom, and redraw after a disposable edit followed by
   native Undo/Redo. Recheck context after master and foreground-document changes;
   verify label/marker placement at actual zoom instead of assuming a viewport
   coordinate example guarantees visible output. Display options must not add Undo entries or alter font
   userData or selection. Keep pure calculations separate from native checks.
6. For a changed artifact, show the revision diff and validate it. Apply the
   decision above to installation/relaunch, then repeat the affected proofs.
   If old behavior remains, check workspace versus installed paths and the
   loaded class/version before another write. Fix the concrete workspace error;
   do not invent MCP reload commands or modify the bridge.
7. For authorised cleanup, disable/remove only the owned plugin, close only
   disposable fonts and verify unrelated settings/files and baseline bytes.
   Record crashes and failed cleanup; do not count them as passes.

Use the [compact verification record and failure-specific recovery steps](verification-and-recovery.md)
to report a revision or resume an interrupted test. These are project guidance;
the qualified menu observations above apply to Glyphs 4.1 (4107).

Supported MCP jobs have existing Undo/discard behavior. That is not recovery
for arbitrary plugin code. Identify public task calls and independent proofs
separately in the report.

Return to font work using the existing `$glyphs` context, without reloading it.
Rediscover after bridge/Glyphs restart;
otherwise retain a valid document ID for the same intended font. Selection
reads need no job or Save. Missing private capabilities require coordinated
updates, not substitute workflows.
