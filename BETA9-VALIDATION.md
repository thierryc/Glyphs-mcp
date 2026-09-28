# Beta 9 preparation — build 51

Date: 2026-09-28. Source branch: `lit/v2-beta`.
Product version: `2.0.0`; release identity: `2.0.0-beta.9`.

## Scope

Setup includes a Beztrace card and a separate setup-details sheet. It shows the
independent plugin's version (0.1.0/build 2), Glyphs and Python requirements,
engine release link, development availability and Path → Trace Image workflow.
The source reference is Beztrace commit
`45b1108fb7f51d5877c964a296a867412eb167cb`.

The current companion artifact is unsigned, unnotarized and native-unqualified.
The card provides information and setup links; it does not install, update,
remove, or infer loaded status for the plugin. Beztrace is excluded from the
bundled component plan and Install All. Its external engine and source repository
are unchanged. An explicit development-install workflow is not implemented.

## Verification

- Desktop Setup tests: 22 passed, including exclusion of external Beztrace from
  bundled install/update/removal plans.
- Version-bump tests: 6 passed.
- Managed skill synchronization: 11 verified; lean package check passed with
  12 public tools and both runtime architectures.
- Fresh unsigned Debug app build and source-bound bundle verification passed.
  Candidate: `dist/local/Glyphs MCP.app`; receipt: `dist/local/build-receipt.json`.
- Opened the local build and verified the native Setup version label reads
  `2.0.0 Beta 9 · Build 51`. Visually checked the Beztrace card in the existing
  grid and the complete setup sheet. Escape dismisses the sheet correctly.
- No runtime component installation, engine installation, Glyphs restart or font
  mutation was performed. The copy in Applications remains unchanged.

The full local release gate passed: 2,464 Python tests (two skips, five
warnings), 220 desktop tests, deterministic payloads, both private runtimes,
package/skill checks and the documentation build. The initial gate found two
stale Beta 8 metadata references; they were corrected and synchronized, their
17 focused tests passed, and the complete gate then passed.

Narrow-window/dark-mode review, cross-machine checks and the exact signed-update
trial remain unperformed. The user approved publication with these limits.
Signing and notarization are in progress. Carry forward the outstanding acceptance limits documented in
[BETA8-VALIDATION.md](BETA8-VALIDATION.md).

## Distribution

Beta 8/build 50 remains the published signed and notarized prerelease. Its exact
appcast and release assets are unchanged. The user approved signing and publication after reviewing this note. Source
commits are `35387474` and `8d71cbeb`; the signed tag and distribution evidence
will identify the final candidate. Stable Latest remains unchanged.
