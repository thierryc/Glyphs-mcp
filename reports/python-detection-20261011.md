# Glyphs default Python detection investigation

Date: October 11, 2026. Source changes and a verified unsigned local desktop
candidate. Guest installations and preference changes were performed in the
authorized VirtualBuddy test VM; the host development installation was preserved.
No commit or publication was performed.

## Finding

The installer preflight and runtime dependency inputs are unchanged between
`v2.0.1` and `v2.0.3`. Both pin glyphs-cli 0.6.1 and private sidecar CPython
3.14.7. The retained arm64 CLI binaries in `build/private-runtime-201` and
`build/private-runtime` have the same SHA-256:
`520e96e0c0e6592b76583b02191a4de2d2b811b7028b52cb0c8e7cfcd7297ace`.

glyphs-cli depends on the selected app's `GSPythonFrameworkPath` preference.
It fails with `No Python framework path configured.` when the setting is absent,
even if the official Plugin Manager Python framework is installed. Supplying
that framework with `--python` works. The [upstream CLI documentation](https://pypi.org/project/glyphs-cli/0.6.1/)
documents this explicit framework selector. Glyphs' own [Python setup instructions](https://forum.glyphsapp.com/t/glyphs-4-python-issues/36638)
identify the Plugin Manager module and the `(Glyphs)` selection.

This is a reproduced detection gap, not evidence of a new 2.0.3-only regression.
Prior 2.0.1 qualification used Glyphs 4.1.1/build 4108 with Glyphs Python 3.14.6.
The current host uses Glyphs 4.2/build 4201 and the same Python version. A changed
preference or Glyphs setup is a plausible explanation for different behavior.
The original reported 2.0.3 error was not supplied, so its exact cause remains
unconfirmed. The maintainer subsequently clarified that the other Mac detects
the installed Glyphs Python module but fails a setup check and cannot install.
The missing-preference reproduction does not establish the cause of that
Mac's failure.

## Change

One standalone resolver is shared by installer preflight, the sidecar native
worker and Reference Inspector. It reads the exact selected application's
preference domain. If that setting is absent, it resolves the official Glyphs 4
module at `Library/Application Support/Glyphs 4/Repositories/Python/Python.framework/Versions/Current/Python`
in the user's home or the system installation and supplies the resolved
framework to glyphs-cli. Existing explicit selections, including broken or
disabled selections, retain the CLI's existing behavior. Preference read errors
do not silently switch interpreters. The private sidecar Python remains separate.

The current host already selects the Plugin Manager framework's `3.14` directory;
there was no need to change that preference.

### Installation override and Setup hierarchy

A failed scripting check now offers **Allow installation anyway** after payload
preparation has succeeded. This enables component installation for the current
session and the same selected Glyphs application; it never reports Python as
verified. **Check again**, a changed Glyphs application or a new app session
returns to normal checking. Component installation passes
`--skip-python-check` to the backend, so the check is not repeated there.
`--preflight-only` always performs its check, even when the skip flag is present.
Payload identities, closed-Glyphs checks, service guards and transactional
recovery remain enforced.

Initialization status is inside Setup's bounded content column instead of an
inset across the entire window. Python has one compact status card with a short
summary, actions and a collapsed **Check details** disclosure. Raw errors and
timing details no longer dominate the window or appear on other pages. English,
French and Chinese strings include the recovery option.

## Verification

- 155 targeted Python cases passed: detection, installation, native worker
  errors, Reference Inspector, payload builds, sidecar, protocol and desktop
  installation/build checks. The override tests cover successful component
  installation after opting out, mandatory preflight-only checks, and continued
  refusal of running Glyphs or corrupted payloads.
- 5 focused desktop tests passed, including the explicit-choice state gate and
  refusal to bypass payload preparation failures.
- A temporary app wrapper referenced the existing Glyphs resources but used
  the beta bundle identifier, whose Python preference is absent. No installed
  app files or preferences were changed. Both retained CLI binaries failed
  identically without an explicit framework.
- The updated preflight loaded its resolver from a temporary payload and passed
  for that wrapper, reporting Glyphs Python **3.14.6**.
- The same preflight passed for the actual selected `/Applications/Glyphs 4.app`.
- Automated checks verified no bytecode or payload identity changes during
  preflight, and that both native task launchers include the framework selector.

Host checks covered Python startup and `GlyphsApp.GSFont` import on Apple
Silicon. Later VM checks covered fresh installation and native jobs; see the
matrix below. No physical Intel run or exact signed distribution qualification
was performed. UI interaction testing
was stopped after the automation tool hung and macOS denied assistive access.
A screenshot of the candidate's initial project page was saved at
`/var/folders/x5/fygm197n4zg2k5l0shskngr80000gr/T/codex-shot-2026-10-11_15-31-51.png`;
it does not qualify the new Setup states visually.

## Local candidate

- App: `dist/local/Glyphs MCP.app`.
- Receipt: `dist/local/build-receipt.json`; reverified against current sources.
- Test ZIP: `dist/local/Glyphs-MCP-python-check-local.zip`, 171,111,958 bytes.
- ZIP SHA-256: `435321ed008289ae87f4f4c6f0b4ddc578f5fc7b6845045651cf8fb12dffa6e8`.
- The ZIP executable, installer helper and default-Python resolver were compared
  with the verified candidate. The app was built by `scripts/build_local_app.py`.
- This is an unsigned Debug test candidate retaining version 2.0.3/build 59,
  not a published release. A DEBUG-only `--qualify-python-check-failure` launch
  argument can simulate the failed scripting check for manual recovery tests.
  The currently running local candidate was confirmed to have no such argument.

## Fresh VirtualBuddy installation test

The user authorized resetting the open VM to test a fresh Glyphs/Python/MCP
installation. Read-only host inspection identified the sole active guest as
`/Volumes/T9/VM/Copy of glyphs-base.vbvm`. Its virtual NIC MAC
`<vm-nic>` matches the DHCP lease `<vm-address>` (`testerslMachine`).
The user enabled Remote Login and the requested RSA key was verified as the
guest's sole authorized key. Existing software was moved into a recovery folder
before the authorized reset. No other VM or host Glyphs installation was reset.

The no-Python case, official Glyphs module and stock python.org installer have
now been exercised. See [the VM matrix](python-matrix-vm-20261011.md) for exact
versions, normal and override installation results, the separate FontTools
export-worker dependency gap and incomplete GUI checks. The official module was
installed from its fresh upstream asset at the default repository path; Plugin
Manager UI installation itself was not automated. Stock python.org loads but
lacks PyObjC (`objc`), so its normal scripting check correctly fails. The official
Glyphs module and selection were restored after the comparison.


October 12 update: the user supplied the original error log. Its repeated
`No Python framework path configured.` matches the reproduced missing-setting
failure. It does not identify which copy or settings domain the other Mac used.
Detailed diagnostic logging and alternate-domain VM evidence are described in
[the installation logging report](installation-logging-20261012.md).
