# Glyphs MCP 2.2.0 / build 67 qualification

Source candidate: `63432c65c4c29a2a05fe35cf6e8447d24b8aacd2`. The later evidence
commit changes release records only. Published 2.1.0 assets and feeds are unchanged.

## Passed

- Full gate: 3,144 Python tests, two skipped; 298 desktop tests; documentation,
  deterministic payloads, skill synchronization and package consistency.
- Ten externally supervised subprocess cases using actual production code,
  under normal and single-worker Swift scheduling. Build 66's restricted-pool
  reproduction hung beyond its own deadline; build 67 passed.
- Expanded payload, universal app and disk image accepted by Apple and stapled.
  Final signature/Gatekeeper/package/archive/feed verification passed, including
  94 Mach-O files and 47 bundles. Both final private runtimes passed; Intel code
  ran through Rosetta.
- Actual signed Sparkle 66 → 67 replacement and relaunch in VirtualBuddy.
  Exact final archive; separately signed local test feed; validations unchanged.
  User completed the guest macOS authentication prompt. Public GitHub transport
  was not exercised. See `vm-signed-upgrade.json`.
- Actual build-67 production Setup: native Python 3.14.6 check completed in
  1.84 seconds after about 160 seconds of VM payload preparation. The prior
  indefinite helper-launch stall did not recur. See `vm-setup.json`.
- Retained installed build-66 native edits/recovery, Save, history clear/restore
  and non-orphan guards; see `native-build66-retained.json`. The harness's initial
  incorrect recovery-menu expectation is explicitly recorded there.
- Retained build-66 orphan archival/retention against a real native bridge, in a
  separate diagnostic job store. Synthetic orphan records never launched native
  edits. The retention clock was supplied only to that isolated store. Font bytes
  and canonical diagnostics stayed unchanged; see
  `native-archive-build66-retained.json`.
- Actual native compact palette title observed as “Glyphs MCP Bridge”, Ready.

## Migration follow-up and final acceptance

The original desktop migration attempts timed out; their operation IDs,
rollback and byte-for-byte reconciliation remain in
`vm-component-migration.json`. A later invocation of the exact final signed
installer CLI passed every production check and committed build 67 in 18.86
seconds. No timeout or validation was relaxed. See
`vm-component-migration-cli.json`.

After a normal companion restart in the VM, desktop Setup passed its native
Python check again. The installed final build-67 bridge and sidecar then passed
17 native checks: receipt-matched identities, exact targets and untouched controls,
unchanged outlines, no implicit save, selective undo, the existing dirty-document
save guard, verified Save and closed workflows. See `native-build67.json`.
The initial harness assumed undo would clear the native dirty flag; it resumed
through the existing save guard, without bypassing protocol validation.

Final exact notarized build-67 desktop component migration passed in **9.311
seconds**, including native preflight in 0.750 seconds, installed import checks
and normal service restart. The progress window was minimized in VirtualBuddy.
Earlier visible-window attempts timed out and remain recorded. Process sampling
showed heavy WindowServer load; graphics contention is a supported inference,
not a proven root cause. A diagnostic activity/QoS guard did not fix visible-window
failures and was excluded from production. No timeout or validation was relaxed.
See `vm-final-desktop-migration.json`.

Fresh post-migration native reads verified both build-67 running identities
against the installed receipt, all 22 tools, exact A/B widths 616/600, unchanged
fixture bytes and only committed/restored journals. The first read-only check
waited behind Glyphs' trial reminder; it passed after continuing the previously
accepted trial. No font write was performed in this follow-up.

Invalid signed feed rejection and an interrupted archive download passed on the
exact notarized app, with its executable unchanged. Native UI showed signature
validation and download errors respectively. See `vm-adverse-updates.json`.
Cancelled native Glyphs closure also passed: Cancel preserved the unsaved fixture
and blocked installation; subsequent Don't Save closed the editor with persisted
source unchanged. See `vm-cancelled-closure.json`.

The native acceptance phase is complete with the VM limitation above. Public
release/tag/feed verification remains a separate publication phase. The working
host Glyphs session was not changed or restarted.

Physical Intel hardware is unavailable. Exact macOS 14.0 and broader
client/accessibility/localization coverage retain their earlier limitations.

The sidebar experiment's 20 fresh VM runs were clean, including baseline:
**not reproduced**, mitigation effectiveness unproven; automatic suppression off.

## Evidence and artifacts

`qualification.json` contains source hashes, full-gate identity, accepted Apple
submission IDs, final runtime results and distribution checksums.
`process-runner-regression.json` contains the external supervisor results.
Full local logs and native call records are retained under
`build/release-2.2.0-build67-final/` (untracked build evidence).

Final local artifacts:

- `dist/installer-app/Glyphs MCP.app`
- `dist/Glyphs-MCP-2.2.0.dmg`
- `dist/desktop-update/Glyphs-MCP-2.2.0.zip`
- `dist/SHA256SUMS`

Earlier build-66 artifacts remain in `dist/archive/2.2.0-build66/`.
No public release tag or signed-feed promotion was performed.
