# 2.0.0 Beta 1 — pre-push validation

Status on 8 September 2026: **local release gates and unsigned VirtualBuddy
installation acceptance passed for 2.0.0 Beta 1, build 43.**

## Verified locally

The complete `scripts/run_local_release_tests.sh` passed after the fixes below,
using the repository's `.venv-v2` Python interpreter:

- 1,238 Python tests passed; 2 skipped (Copilot CLI unavailable and the optional real-AppKit drawing context not enabled).
- 167 macOS installer tests passed.
- Both ARM64 and Intel private runtimes started, exposed the then-current HTTP
  catalog and supported the stdio proxy without package downloads.
- The actual packaged installer entry point ran successfully on both runtimes
  from a temporary directory without the source checkout on `PYTHONPATH`.
- Deterministic payload comparison, documentation build, source version checks,
  bundled skill synchronization and whitespace checks passed.
- The unsigned app and payload identify as 2.0.0 Beta 1, build 43. Glyphs 3's
  packaged component remains 1.11.0.

Four agent plugin tests still expected the unpublished 2.1.0 version. Their
expectation now comes from the canonical release identity. More significantly,
the packaged installer imported a build-only version module that was not
shipped. Moving that import into the build function fixes installation without
adding repository metadata dependencies to the runtime. The release gate now
executes the packaged installer directly to detect this class of omission.

## VirtualBuddy acceptance

The running VM is **Copy of glyphs-base**, macOS **26.6.2 (25G83)**, ARM64,
account `tester`, with Glyphs **4.1 (4107)**. The beta frontend was launched
from `~/Downloads/Glyphs MCP Beta Fixed.app`. The existing desktop application
in `/Applications` was kept; the installed runtime and all three Glyphs 4
components were upgraded through the beta frontend.

The initial unsigned archive exposed the packaged installer import failure
above and is superseded. Its staged app, `Glyphs MCP Beta.app`, must not be
used for acceptance. The corrected app is built locally at
`/tmp/gmcp-beta-vm-repaired/Build/Products/Debug/Glyphs MCP.app`.
Its test archive is `/tmp/gmcp-beta-vm-transfer/repaired.zip`, SHA-256 verified
in both host and guest:

```text
fab7af8a6042ed5fe209f8d68000336aa148571aa5028986e8958b6486eb6e15
```

The following checks passed using this corrected archive:

- Packaged installer entry point, bundled Python and Glyphs native scripting
  preflight in the guest.
- Fresh installation of MCP, Curve Inspector and Reference Inspector into a
  disposable home. Receipt: version 2.0.0, build 43. An unrelated test file in
  the plugin directory was preserved.
- Desktop app upgrade of the VM's existing 2.1.0/build 42 installation to
  2.0.0/build 43, reaching the Ready screen.
- Desktop app removal of Curve Inspector, preserving MCP and Reference
  Inspector, followed by restoration of Curve Inspector.
- All installed file identities matched their receipts after upgrade, removal
  and restoration. The service started and exposed the exact then-current
  catalog after each operation; `get_status` succeeded.
- Port 9680 and automatic startup disabled were preserved across all three
  desktop operations. The previous receipt said automatic startup was enabled,
  but the backed-up launch-agent plist had it disabled. The check compares the
  effective launch-agent settings, which correctly take precedence.

Evidence: `build/beta-vm-validation/vm-fresh-install.json`,
`vm-after-upgrade.json`, `vm-after-remove.json`, `vm-after-restore.json`, and
`vm-setup.log`.

## Disposable-font acceptance

The installed beta was exercised through its public MCP endpoint inside the
VM, using a copy of `headless-preview-minimal.glyphs` in the guest Downloads
folder. `get_status` and `list_documents` confirmed the live bridge and exactly
one open, clean disposable font before the job was prepared.

A single width change for glyph A passed the complete sequence:

| Operation | Verified width |
| --- | ---: |
| Prepare (live font unchanged) | 600 |
| Apply | 625 |
| Glyphs native Undo | 600 |
| Glyphs native Redo | 625 |
| Whole-job discard | 600 |

The outline hash remained identical at every stage. The saved source's
SHA-256 remained identical throughout; no Save or export was performed.
Undo and Redo were invoked through the native Glyphs Edit menu, and discard
reconciled the same job identity after Redo.

Observed `get_status` HTTP round-trip timings in this VM:

| Phase | Samples | Median (ms) | 95th percentile (ms) | Maximum (ms) |
| --- | ---: | ---: | ---: | ---: |
| Idle baseline | 10 | 14.285 | 19.686 | 19.686 |
| During preparation | 99 | 16.257 | 43.290 | 46.838 |
| During application | 10 | 26.479 | 83.876 | 83.876 |
| During discard | 10 | 24.509 | 43.552 | 43.552 |

These are smoke-test observations for one glyph, not a large-font performance
qualification or measurements of native execution alone. Evidence and the
repeatable guest runner are in `build/beta-vm-validation/vm-font-*.json` and
`font.py` / `font.sh`.

## Release boundary

The candidate remains on local branch `lit/v2-beta`. No GitHub push, tag,
signing, notarization, release upload or publication was performed. The beta
registry and appcast target that branch, but their public availability cannot
be tested until the branch and release assets are published.

These unsigned functional checks do not prove Gatekeeper, notarization,
signed updates, or clean installation from a quarantined public download.
The VM covers ARM64/macOS 26.6.2; Intel runtime checks ran on the host, not on
a separate Intel Mac. Signed distribution acceptance remains a later release
step. The host-installed app was not replaced during that VM validation.

The disposable font was closed without saving after restoration.
The VM is left running with all three beta components installed. Temporary
host-to-VM transfer and report listeners are stopped after evidence collection.

## Host installation and candidate cleanup — 10 September 2026

The host now uses **2.0.0 Beta 1, build 43** for both the desktop app in
`/Applications/Glyphs MCP.app` and the Glyphs 4 components. The desktop was
rebuilt locally with signing disabled; its bundle metadata, beta channel and
complete installer payload passed verification. The launched Overview shows
`2.0.0 Beta 1 · Build 43`, MCP Ready on port 9680, and all three components
installed. Component file identities, bridge connectivity and worker
availability were verified after restarting Glyphs 4. No font was changed.

The obsolete 2.1.0 desktop app and 87 generated candidate artifact groups were
removed, including old apps, ZIPs, DMGs, component payloads and update metadata.
The obsolete local Latest DMG was verified byte-identical to the 2.1.0 DMG
before removal. The current beta payload and installation recovery data remain
available. `build/beta43-cleanup-report.json` records the removed artifacts.
The current changelog consolidates desktop development under Beta 1; historical
qualification records retain their original tested versions.
