# Dirty-indicator investigation

Investigate the installed private lean v2 without changing product code, skills,
Undo registration, autosaving or user fonts. Keep HTTP and fractional-node
restoration separate. No forced clean flag, implicit Save or history clearing.

Use fresh copies of the reproducible one-master, two-glyph fixture. Integer width
edits isolate dirty tracking from node rounding; fractional outlines, metadata,
anchors and real hint links are preservation controls. Use native UI for the
ordinary edit/Undo arm and public jobs for the v2 arm. Diagnostic scripted edits
and explicit native-manager invocations, if needed, are separately labelled.

Compare clean-open, Edit View without mutation, width edit, Undo, Redo and final
Undo. Observe dirty state immediately/as soon as captured and after event-loop
settling, including beyond the recorded native autosave delay. Record native
isDocumentEdited, hasUnautosavedChanges, window state, glyph change counts, and
document/glyph Undo manager identities and states separately. No unavailable
selector is interpreted as zero. Record native autosave state without changing it.

Require exact font-data, native-object and hint-reference preservation/restoration;
record derived bounds independently. Check unrelated glyphs/documents, originally
dirty edits, and v2 discard after an unrelated edit. A dirty-before-job refusal
is expected and must preserve those edits. Repeat clean native/v2 cases on fresh
copies before assigning cause. Retain all failures and unsupported controls.

Temporary setup/read-only observation uses existing qualification patterns.
Do not patch native methods or adjust counters in the primary controls. Capture
first uninstrumented/simple observations before considering extra instrumentation.
Remove any temporary helper and observers before closing their owned fonts. Stop
on a new crash and preserve evidence; no automatic restart or autosave workaround.

Report measured facts separately from inference. A native UI reproduction with
plugins loaded does not establish exclusive host causation. Propose a correction
only if it fits existing native hooks and preserves unrelated history/dirty state.
