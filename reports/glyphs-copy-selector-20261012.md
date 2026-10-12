# Glyphs 4 copy selector

Date: October 12, 2026. Local unsigned candidate; no commit or publication.
Existing detection, installation override, Setup layout, export and diagnostic
logging changes are preserved.

## Behavior

Setup shows a Glyphs 4 application picker only when more than one distinct,
supported Glyphs 4 copy is detected. Menu entries include name, version and
path. Same-version copies remain distinct by their URLs; aliases of the same
physical bundle are deduplicated. Glyphs 3 does not count toward the picker.

The selected path is remembered in the app's preferences and retained on refresh.
If it disappears, the existing stable/system-directory/path priority supplies a
fallback. The selected application drives Open Glyphs, Plugin Manager, Python
preflight and component transaction arguments. Installation records that exact
application for the external worker. Picking another copy alone does not restart
or retarget an already-running service; an MCP install/update records the choice.

Python status shows the selected application and its native interpreter version
and framework/prefix path, identifying the official Glyphs module where
applicable. Private MCP Python is never used as the displayed Glyphs version.
Changing copies immediately clears previous readiness, detection and session-only
installation overrides, cancels the prior check and starts checking the new copy.
Per-check UUIDs reject late results, including switching A to B and back to A.

The shared Glyphs 4 plug-in directory means an open copy can still own managed
files. Desktop component controls and the backend therefore require all Glyphs 4
copies to be closed. The normal Quit action requests termination of those copies
and lets their native save dialogs run. Glyphs 3 remains outside this guard.
Recognized Glyphs 4 beta IDs are supported, including the older generic beta ID
only when its version identifies Glyphs 4; Glyphs 3 is rejected before writes.

## Verification

- 146 focused Python tests passed, covering default/beta Python detection,
  protected Glyphs 3 routing, exact selected-app receipts/worker arguments,
  other-copy process guards, installation, export, payload and desktop builds.
- 11 focused desktop tests passed, including zero/single/multiple-copy visibility,
  retained and missing choices, native/private Python distinction, reset of
  overrides and detection, and rejection of late checks.
- The exact candidate ran in the identified VirtualBuddy guest. A prior disposable
  logging probe was also found through Launch Services; its original Info.plist
  was temporarily masked for the controlled single-copy case and restored.
- Single copy: the Setup picker was absent; native Glyphs Python 3.14.6 and its
  official module path were visible. Multiple copies: the picker was present,
  the selected test copy was shown, and its deliberately selected stock python.org
  framework path was displayed with the actual missing-objc check failure.
- The backend rejected an attempted skip-check installation aimed at the test
  copy while the real Glyphs 4 app remained open, before component replacement.
- Host screenshots of the VM window were inspected without UI automation. Guest
  screen capture was unavailable; the existing host Screen Recording permission
  was used. Picker menu clicking and rapid UI switching were not automated;
  the check-state transitions are covered by desktop tests.
- Temporary test-copy files, beta Python preferences, saved app selection and
  the prior probe metadata were restored. No fonts or installed components were
  changed by this UI qualification. The original Glyphs app/service stayed running.

Screenshots (inspection files in temp):

- Single: `/var/folders/x5/fygm197n4zg2k5l0shskngr80000gr/T/codex-shot-2026-10-12_09-46-13.png`.
- Multiple: `/var/folders/x5/fygm197n4zg2k5l0shskngr80000gr/T/codex-shot-2026-10-12_09-47-14.png`.

Raw VM records and test logs: `build/copy-selector-tests-20261012/`.

## Local app

- App: `dist/local/Glyphs MCP.app`, opened for manual testing.
- ZIP: `dist/local/Glyphs-MCP-copy-selector-local.zip`.
- Unsigned Debug 2.0.3/build 59; not a published release.
- Source SHA-256: `02e137847fd6e7b38b8c1b1f5fe974a39af4c41f2e680eca14c0b794ca02eac2`.
- App SHA-256: `b296120bc54b1a0f31fce63fb3f4c5d88a9ad792b9b9fb6e571c03428ccc8543`.
- ZIP SHA-256: `a366219b8e55847c11e42898f62efaff744b4be5f97f41ea7fc897c969c3e53e`.
- Current source and full app match `dist/local/build-receipt.json`.

English, French and Chinese UI strings include the picker, interpreter labels
and shared-copy guidance. `git diff --check` is clean. Host components were not
installed or restarted during this task.
