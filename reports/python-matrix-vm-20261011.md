# Fresh VM Python matrix

Guest: `Copy of glyphs-base`, macOS 26.6.2/build 25G83, VirtualMac2,1,
account `tester`, IP `<vm-address>`, NIC `<vm-nic>`.
The active VM disk and DHCP identity were verified before any reset.
SSH login works with the requested host RSA key. The guest has one authorized
key, fingerprint `SHA256:1hnQuTYXSflIQS10SXMirUsVe8uP0NxIIjlSxjV84yM`, matching
the host's `id_rsa.pub`. No extra authorized keys were found.

The existing service was stopped through its control lifecycle. Guest Glyphs,
default Python, MCP support directory, components and agent were moved to
`~/Desktop/GlyphsPythonFreshTest/pre-reset-installation` for recovery. The guest
OS, account and host installation were retained. The official current Glyphs
download is 4.1.1/build 4108. The test manager is the verified unsigned local
2.0.3/build 59 candidate; its archive hash matches the host candidate.

## Results

| Environment | Result |
| --- | --- |
| Neither Glyphs Python nor python.org Python installed | Preflight rejects scripting with `No Python framework path configured.` No installation receipt is created by the check. |
| No external Python, explicit installation override | MCP, Curve Inspector and Reference Inspector install. The private sidecar runs, advertises 20 tools matching its status catalog, and correctly reports the bridge unavailable. This does not enable native font scripting. |
| Fresh official Glyphs Python 3.14.6, no saved framework preference | Updated preflight succeeds and normal installation of all three components succeeds. This exercises default-module discovery. |
| Official Glyphs Python selected for the GUI | Live bridge and sidecar both run at 2.0.3 and their loaded hashes match the installed receipt. Eighteen read capabilities and both companions are advertised. |
| Official Glyphs Python, headless native worker | Feature compilation succeeds with source hashes unchanged. Native TTF and WOFF2 generation succeeds, but the export worker fails its verification stage because FontTools is absent from this Python environment. The generated fonts parse successfully with FontTools in the private sidecar runtime. |
| Official Glyphs Python, native Reporter entry points | Both Curve Inspector and Reference Inspector pass the existing bounded native SDK/selector checks. Visible canvas redraws were not tested. |
| Stock python.org Python 3.14.8, official Glyphs module moved aside | The framework loads, but native startup, preflight and normal installation fail with `ModuleNotFoundError: No module named 'objc'`. The stock installer alone lacks Glyphs' PyObjC prerequisite. |
| Stock python.org Python, explicit installation override | All three components install successfully. The native worker still fails with missing `objc`; bypassing the check does not repair scripting. |
| Official Glyphs Python restored | The 3.14.6 preflight passes again. The official module and exact framework preference are restored; python.org remains installed separately. |

The official Glyphs module ZIP was freshly downloaded from the exact upstream
origin recorded by its Plugin Manager installation:
`https://github.com/schriftgestalt/GlyphsPython/releases/download/python-3.14/GlyphsPython.zip`.
Its framework was placed at the standard module location using `ditto`.
The Plugin Manager UI itself was not automated or qualified.

## Fresh-machine dependency finding

`font_export_job.prepare` imports FontTools inside the external Glyphs Python
worker, while FontTools is bundled in the separate private MCP interpreter.
A clean official Glyphs Python environment therefore reaches native generation
but returns `ModuleNotFoundError: No module named 'fontTools'` during export
verification. The private runtime can parse both generated files, confirming
that native generation succeeded. This is a separate reproducible dependency
gap; it does not establish the cause of the other user's initial setup error.
This initial finding was subsequently fixed and verified in the October 12
local candidate; see [the export fix report](fonttools-export-fix-20261012.md).

The initial export fixture used format 3 and lacked persistent instance IDs.
The final dependency reproduction uses a normalized format-4 disposable font.
Intermediate harness errors were corrected without changing product code.

## Editor check and recovery

A disposable `open_document` request returned `glyphs_busy` with an uncertain
outcome. The bridge remained reachable, with no documents and zero active
operations in the subsequent read. No new-key Open retry or forced restart
was performed. Retained opening:

- Open ID: `open_672465f01ed57e7cca1919e7909d9d5e43c14c14a1d5429d7c20d77271607ace`.
- Path: `<guest-home>/Desktop/GlyphsPythonFreshTest/Fixture.glyphs`.
- Bridge session: `3778e33cd3e0481b98bc52ba9cc94bfe`.

The original opening was later reconciled through the retained request to the
exact clean fixture document. The next smoke client stalled before persisting
any result and its exact client process was cancelled. Bridge reads confirmed
zero active operations, no saved-job records, and the fixture unchanged at its
original path and generation. It was closed through the supported bridge Close
lifecycle; the retained request and result confirm no unsaved changes were
discarded. Native Quit timed out but completed later, and the standard idle
service controller then stopped successfully. No forced Glyphs termination or
idle-guard bypass occurred. GUI width apply/restore and Save As remain
unqualified. UI automation was skipped after the earlier hangs. No user font
was edited.

## python.org installer

The selected comparison is the current Python 3.14 maintenance release, matching
the minor version of Glyphs' module: [Python 3.14.8](https://www.python.org/downloads/release/python-3148/).
The package is present in the guest at:
`~/Desktop/GlyphsPythonFreshTest/inputs/python-3.14.8-macos11.pkg`.

- SHA-256 matches the published checksum:
  `507fc086c5c006ff875d344a75b4e67b8fb3c401f1bc4908c6250adb673d4907`.
- `pkgutil --check-signature` reports trusted notarization and Developer ID
  Installer: Python Software Foundation (`BMM5U3QVKW`).
- The user installed the package with administrator authentication in the VM.
  Package receipts confirm installation; its executable reports Python 3.14.8,
  arm64, prefix `/Library/Frameworks/Python.framework/Versions/3.14`.
- Stock Python has neither `objc` nor FontTools. No pip packages were added, so
  this tests the official installer as supplied.

The official module was moved aside and the exact python.org framework selected
for preflight, normal installation, override installation and native-worker
checks. All native failures identify missing `objc`, rather than a missing
framework. The official module and preference were restored with an exit guard.
The private service was explicitly started through its controller after the
comparison. Guest authorized keys were rechecked: the same single key remains.

Final controller status confirms the service is running at port 9680. After
Glyphs relaunched, the bounded final MCP client check timed out and the direct
bridge status read reported unavailable. The earlier successful live bridge
identity check is retained, but post-restoration live editor readiness remains
unqualified. The restored module, selection and headless preflight are verified.
No further UI automation was attempted. The VM remains ready for manual startup
dialog checks, with no retained open test font and its recovery folders intact.

## Local candidate checks

155 focused Python tests and five focused Swift desktop tests passed for the
source changes. At handoff, both the source digest and full app bundle digest
match `dist/local/build-receipt.json`; `git diff --check` is clean. Setup layout
and recovery-state visuals still require manual review of the unsigned Debug
candidate. No source changes were made for the separate export dependency gap.

## Evidence

Raw guest reports are retained in
`build/vm-python-matrix-20261011/evidence/reports/`. Guest inputs, recovery state
and disposable artifacts remain under `~/Desktop/GlyphsPythonFreshTest`.
The verified local test app and ZIP remain at `dist/local`.
