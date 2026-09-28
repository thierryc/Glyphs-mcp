# Beta 8 combined local candidate — September 28, 2026

Published release: [Beta 8](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.8), build 50.
Signed tag source: `bf0ef6cd` on `lit/v2-beta`; implementation commit: `3cf956ab`.
The checkpoint workspace and all existing milestone work were consolidated
in one commit. Stable `main` is unchanged. The beta feed now serves the verified Beta 8 archive.
Local-only AGENTS guidance and `.codex-local/` remain excluded.

## Verification

- Complete `scripts/run_local_release_tests.sh`: passed. 2,464 Python tests,
  two skips, five warnings; 219 macOS desktop tests, zero failures.
- Both private runtime architectures, deterministic payload construction,
  eleven-skill synchronization, twelve-tool package checks and website build pass.
- The first gate run found one stale source assertion for the checkpoint-aware
  loading message. It was updated, its 20 focused tests passed, and the complete
  gate passed on the committed source.
- Installed actual-editor kerning lifecycle: 36 cases per font format, 72 total.
  See `../beta8-milestone8/editor-{glyphs,glyphspackage}.json`.
- Installed Codex connector: complete 22-page English/French proof traversal,
  exact-edit preview/apply, Keep and Save. Direct HTTP harness latency is separate
  from connector transport. Glyph-pair native UI Undo/Redo passes.
- Group-pair ordinary UI Undo did not change the tested value in Edit or font
  view. This is an unresolved acceptance check, not a passing document-manager
  test. Its original zero value was restored through the typed workflow and saved.
  Outline hashes and widths of A, V and n remained unchanged.

## Local installation

- MCP-only transactional installation completed from `build/simple-native-scripting`.
- Loaded sidecar: `sha256:40e3344a89687224d514fb34d38df6018c60c9e38710efe74064d51b48326752`.
- Loaded bridge: `sha256:c853dee2cd1bbf400ab03ba06ff2312a9bffd9b820aea92835593ee79421a1c7`.
- Port 9680, auto-start, project settings and both companion plugins are preserved.
- Fresh local desktop build verified against its source receipt and installed at
  `/Applications/Glyphs MCP.app`. Installed bundle SHA-256:
  `1a1fac6957f27b3469ca0230fd4a52075ff83bd3124ad5ac4b835e41d0d0ec69`.
- Prior app backed up at `build/local-install-backups/beta8-20260928/Glyphs MCP.app`.
  Both embedded runtime trees match, preserving existing build-input links.
- Prior five saved documents reopened; all seven documents, including the two
  disposable M8 fixtures, are clean. Dactylotype was not edited or saved.

The installed desktop UI shows the compact native picker with Today/Yesterday,
20 readable rows, exact timestamp/timezone/revision help and Load older.
Selecting latest produces the explicit empty state. Selecting revision
`925d255e42b718efc2628c1cf32493325c049662` compares to fixed latest
`7f0f71a2d1dda99ee404fec8dccbf40cde4a7ea9`, automatically selects the changed
H glyph, and displays the existing overlay/layer/zoom controls. Action details
and restore confirmation open separate sheets after the picker closes.
Restore was canceled. Working changes returns to the prior `unrelated.txt`
selection and the three working files. No font restoration was performed.
Earlier wide/narrow sample renders and model tests remain separate evidence.

## Initial signed candidate (before notarization)

`dist/installer-app/Glyphs MCP.app` is the universal arm64/x86_64 release build,
signed by `Developer ID Application: Thierry Charbonnel (N9U29A4T8J)`.
Secure timestamp: September 28, 2026, 11:12:43 EDT.
Code directory hash: `bbc071d23ca10bb6c3f6a0185e39fc48c4f1d92c`.
94 Mach-O binaries and 47 bundles passed signature verification.
The locally installed Debug build is separate from this signed release candidate.

The initial automatic-review block was resolved by the user's explicit Apple
upload approval. The user also authorized GitHub publication after the remaining
group/document native UI Undo, exact-pair card visual and signed-update/component-
migration gaps were disclosed. These acceptance gaps remain open.

## Published signed distribution

Apple accepted three submissions: expanded payload, app and DMG. All tickets
were stapled and verified. The final app code directory hash is
`0f89904758972f617ce317abfcfe720a813eb301`, timestamp September 28, 2026,
12:07:50 EDT. Developer ID, hardened runtime, timestamps, nested signatures,
Gatekeeper and signature-preserving installation copies passed.

The guarded publisher repeated the full release gate: 2,464 Python tests
(two skips, five warnings) and 219 desktop tests passed. Both signed private
runtimes and 96 standalone native kerning cases passed. Those native cases
exercise the exact extracted signed source with a disposable fixture save adapter;
they do not replace the actual-editor or unresolved native UI acceptance checks.

The DMG, Sparkle ZIP, signed appcast and SHA256SUMS are public. Fresh unauthenticated
downloads match local hashes; both Sparkle signatures verify. The exact signed
appcast is published on `lit/v2-beta`; Stable Latest remains v1.11.1.

- [Distribution and notarization evidence](distribution-state.json)
- [Public GitHub metadata](github-published.json)
- [Public download verification](public-download-verification.json)
- [Published release notes](github-release-notes.md)
- [Signed runtime checks](signed-runtimes.json)


Local logs/receipts are retained in `build/reports/`: `beta8-release-gate-final.log`,
`beta8-signed-build.log`, `beta8-local-runtime-install.json`,
`beta8-local-app-verified.json` and `beta8-desktop-install.json`.
