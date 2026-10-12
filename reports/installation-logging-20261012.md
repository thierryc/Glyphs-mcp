# Installation diagnostics and missing-framework evidence

Date: October 12, 2026. Unsigned local candidate only. No commit, publication or
host component replacement was performed. The prior detection, install-anyway,
Setup layout and FontTools export fixes are retained.

## What the supplied log establishes

The October 11 log repeatedly reaches verified setup files and then fails during
Python readiness with the exact CLI message `No Python framework path configured.`
It contains no native Python import exception, binary load error or component
transaction result. This localizes the shown blocker to the helper's selected
Python setting, before native scripting startup. Python can still be installed
and usable in Glyphs while that helper cannot resolve its setting.

The log omits the selected app path, bundle ID, preference state and official
module location, so it cannot establish whether the manager checked the same
Glyphs copy the user normally runs. Another version or beta is a plausible cause
of a different preference domain, not a confirmed fact about that Mac. Ordinary
copies with the same bundle identifier use the same user/app preference domain;
[Apple's preference documentation](https://developer.apple.com/documentation/corefoundation/preferences-utilities)
describes the application-ID scope.

The app detector and its stable/system-path selection policy are unchanged
between v2.0.1 and v2.0.3. The desktop model's initialization became asynchronous
and gained timing logs, but retained the same selected-application preflight
arguments. The preflight and pinned CLI inputs were also unchanged, as recorded
in the earlier Python-detection investigation. Repeated quitting/rechecking in
the supplied log never resolved the setting. Duplicate payload-resolution timing
entries are consistent with separate callers waiting on the shared payload;
those timings do not identify an extraction failure.

## New diagnostic evidence

- One session ID per app launch and one check ID shared by desktop and helper.
- App version/build/path, macOS version and process architecture.
- Every detected Glyphs copy, including duplicate versions, and the selected
  path and existing selection policy. Inventory scans /Applications,
  ~/Applications and Launch Services bundle lookup; it is not a whole-disk scan.
  Running Glyphs process paths are also captured when Python checking starts.
- Exact selected app bundle ID, version/build and resolved path; the settings
  domain queried and present/absent/empty/read-error state of only
  `GSPythonFrameworkPath`.
- User/system default-module candidates, existence, resolved paths, explicit
  setting inspection and whether the launcher uses the default module or keeps
  the user's explicit choice.
- Private Python/CLI versions and paths, native Python version/prefix/architecture,
  exit status, bounded captured output, timeout and classified failure reason.
- Explicit installation override and component transaction start/outcome. Helper
  diagnostics are now persisted on successful and failed checks, rather than
  discarded after extracting the generic error. Partial output is retained if
  the desktop process deadline interrupts the helper.
- Shared payload timing entries identify their caller/check and say they measure
  caller wait on cached/shared discovery.

Diagnostics remain in the log and collapsed details. Account home prefixes are
replaced with `~`, standard credential fields are redacted before persistence,
and native output fields are bounded to 8192 characters. No complete environment,
license preferences, authentication files or font contents are collected.
The existing **Copy Redacted Diagnostic Report** action includes the new entries.
Persistent events live at `~/Library/Logs/Glyphs MCP/installer-events.log`.

## Verification

136 focused Python tests and nine desktop tests passed. New coverage checks
missing-setting evidence with a module present, retained explicit selections,
correlated failure/timeout records, bounded/redacted output, duplicate-copy
inventory, and partial stdout/stderr retention on desktop timeouts.
`git diff --check` is clean.

The identified VM used the candidate's exact extracted payload without replacing
its installed components or restarting Glyphs. The official module was retained:

1. Selected stable Glyphs 4 / default module preference: check passes with 3.14.6;
   logs show the exact existing framework and native interpreter.
2. Disposable alternate beta app-settings domain with no preference: bare pinned
   CLI reproduces `No Python framework path configured.` even though the official
   module exists. The updated helper logs `state=absent`, finds the installed
   default module and passes with 3.14.6.
3. Temporarily empty preference in that same disposable domain: the module remains
   present and the explicit empty choice is retained. On this VM native startup
   fails with missing `objc`, classified as `dependency-missing`, rather than the
   absent-setting message. This demonstrates why the preference state and native
   stderr must be recorded separately. The initially assumed test expectation
   was corrected to this actual observation without changing product behavior.

The original beta preference was absent and was restored to that absent state
in a finally block. The stable preference, module, installed runtime, app files
and fonts were unchanged. Raw evidence is retained under
`build/logging-tests-20261012/`. The opened host candidate's persisted
`session.started` event was also read and verified. Full Setup UI automation was
not used; its earlier hangs remain outside these checks.

## Local candidate

- App: `dist/local/Glyphs MCP.app`, opened for manual testing.
- ZIP: `dist/local/Glyphs-MCP-diagnostics-local.zip`.
- Unsigned Debug 2.0.3/build 59; not a published release.
- Source SHA-256: `f1784687f3e55c398378b12a57a1bce6a1982a7c9c5599889bd46c9bef2ab527`.
- App SHA-256: `18797129df235491685d99d1d79fa609dd89bd4b4442aca2ae7acaf561fcd611`.
- ZIP SHA-256: `3e6e916809a3d9e1b9d01fad242c0b069562bc472be88181ead00e724a20a6ea`.
- Build receipt: `dist/local/build-receipt.json`; current source and bundle match.
