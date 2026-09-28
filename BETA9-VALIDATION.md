# Beta 9 release — build 51

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
Developer ID signing and all three Apple notarization submissions passed.
The app and DMG are stapled and accepted by Gatekeeper. All nested signatures
and signature-preserving install copies verified. Both signed private runtimes
passed startup, catalog, packaged installer and proxy checks. The guarded
publisher reran the complete release gate successfully. Carry forward the
outstanding acceptance limits documented in
[BETA8-VALIDATION.md](BETA8-VALIDATION.md).

## Distribution

[Beta 9/build 51](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.9)
is a published signed and notarized GitHub prerelease. Signed tag
`v2.0.0-beta.9` points to `68bf1fdf673285988a886fdf5a3c6471e2f533c0`.
The DMG, Sparkle ZIP, appcast and checksums were downloaded without authentication
and matched the verified local artifacts. Feed and archive signatures passed.
The exact signed beta feed now serves Beta 9. Stable Latest remains v1.11.1.

The user approved this validation scope and explicitly authorized signing and
publication. Beta 8 assets and tag remain unchanged. No Beta 9 app or runtime
was installed over the existing copy in Applications.
See [distribution evidence](reports/beta9-release-candidate/README.md).
