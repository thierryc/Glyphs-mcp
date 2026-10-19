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

## Pending and limits

Production Setup started the build-67 MCP component update after gracefully
quitting the VM editor. Host computer control then became locked. Reconcile the
existing migration before retrying; final installed/running build-67 bridge and
sidecar identity are not yet qualified. The working host Glyphs session was not
changed, installed into, or restarted.

Invalid-signature/interrupted-download/cancelled-closure/failed-migration native
acceptance is not claimed here; keep stable publication separate until reviewed.
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
