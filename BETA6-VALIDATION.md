# Beta 6 preparation record

Source target: Glyphs MCP `2.0.0-beta.6`, desktop build 48, branch
`lit/v2-beta`.

Status: **corrected Beta 6 candidate installed and both requested client
regressions requalified; signed-distribution preparation in progress. Not yet
published.**

The later conversation-workflow implementation and installation supersede the
initial nine-tool/candidate-only state below. See
[the original save UI retest](reports/edit-workflow-20260922/retest/report.md)
for the historical failures and [the corrective retest](reports/beta6-workflow-fixes-20260922/README.md)
for the passing Claude text-save and Cursor remount/slow-permission results.
The broader client and signed-update matrix remains separately qualified.

## Repository preparation — September 22, 2026

- Advanced `release.json`, the installer plist and both Xcode build
  configurations to Beta 6/build 48 using `scripts/bump_version.py`.
- Updated current source documentation and the launch plan. Beta 5 download
  links, its signed `appcast.xml`, and historical qualification records remain
  unchanged. The Glyphs 3 source and frozen documentation remain pinned.
- Preserved the pending automatic-update-check default and README correction;
  recorded that change in the unreleased changelog.
- Removed inspected generated desktop outputs, Python/test caches, website
  outputs and obsolete in-project Xcode build products. Retained dependencies,
  release archives, qualification evidence and the unfinished marketing site
  in `.tmp/v2-marketing-site`.

Local cleanup receipts are in `build/reports/cleanup-20260922T171439Z.json`
and `build/reports/beta6-cache-cleanup-20260922.json`.

## Preparation checks

| Check | Result |
| --- | --- |
| Focused beta identity, version bump, desktop build/cleanup, release security, release skill and documentation tests | 61 passed |
| Lean package contract | Passed: nine tools, eleven skills, both runtime architectures |
| Packaged skill synchronization | Passed for all eleven skills |
| Documentation production build | Passed; Node emitted a localStorage experimental warning |
| Patch whitespace | Passed |

## Dimensions qualification — September 22, 2026

Implemented the negotiated `master.dimensions.read.v1` read and
`master.dimensions.edit.v1` / `dimensions_edit` job using the existing nine
tools. Blank fills require no confirmation; changes to existing values require
exact `approved_overwrites` entries after conversational approval. This is an
assistant-recorded approval, not independent human authentication. Applying
never saves. Writes are enabled only on the qualified Glyphs 4.1 build 4107;
other builds retain reads.

| Check | Result |
| --- | --- |
| Complete Python matrix via local release gate | 2,115 passed, 1 skipped; five existing warnings |
| Final focused Dimensions suite, including eight additional recovery cases | 48 passed |
| Complete macOS installer suite | 203 passed, zero failures |
| Real Glyphs 4.1 (4107) palette and document qualification | 204 checks passed; all 60 native field identifiers |
| Native behavior | Palette setter/clear, live refresh, dirty state, exact document Undo/Redo, whole-job discard, and approval enforcement passed |
| Persistence | Exact metadata survives native save/reopen in both `.glyphs` and `.glyphspackage`; apply/discard leave source files unchanged |
| Deterministic payload builds | Two builds identical; lean identity `sha256:a8ee4dfbe8030550190f7d5b9fb71fbb40c8f217925d83ba206da822968ccfcd` |
| Private runtimes, package and skills | arm64/x86_64 qualification passed; nine tools, eleven synchronized skills |
| Documentation production build | Passed |
| Unsigned Debug desktop candidate | Build 48 validated; release-security check correctly reports `publishable:false` |

The native proof used the real built-in Dimensions palette and a native
GSDocument in an isolated Glyphs CLI process, with disposable fonts. It did not
replace the installed bridge or change user documents. The connected MCP was
separately checked and remains Beta 5/build 47, without the new capability.
This record does not claim live installation or UI acceptance of Beta 6.

Evidence, candidate manifest and source fingerprints are retained in
[reports/beta6-dimensions-20260922](reports/beta6-dimensions-20260922).
The repeatable native check is `scripts/qualify_dimensions_native.py`.

## Pending release qualification

Completion of installed MCP/client acceptance, signing, notarization, Gatekeeper, signed
update/component migration and publication verification remain pending for
Beta 6. Beta 5 results in
[BETA5-VALIDATION.md](BETA5-VALIDATION.md) describe that release only.

## Source integration gate — September 22, 2026

The accumulated Beta 6 changes were committed as `5cd5d667` and submitted in
[PR #52](https://github.com/thierryc/Glyphs-mcp/pull/52), targeting `lit/v2-beta`.
The complete local release gate passed against that source:

- 2,149 Python tests passed, one skipped; five warnings.
- All 203 macOS installer tests passed with zero failures.
- Deterministic payload comparison, both private runtimes, twelve-tool package
  inventory, eleven synchronized skills, and documentation production build passed.
- The unsigned Debug app and build-48 payload verified successfully. This does
  not establish signed, notarized, installed-client or update acceptance.

The source integration does not lift the client-workflow release hold above.
The attempted signed-release preparation was blocked before execution by
automatic approval review, which requested explicit authorization for uploading
the release payload to Apple's notarization service. No Beta 6 release tag,
signed feed or public release assets were created by this integration pass.
