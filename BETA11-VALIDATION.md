# Beta 11 qualification — build 53

Date: 2026-09-30. Branch: `lit/v2-beta`.
Product: `2.0.0`; release: `2.0.0-beta.11`.

## Scope

Beta 11 advances release identity and installer build from published Beta 10.
Current source, packaging, release guidance and the changelog describe Beta 11;
the public catalog remains thirteen tools with eleven managed skills.
No runtime or native font behavior changed in this release.

The font-creation, checkpoint-history and bundled Beztrace engine behavior is
inherited from Beta 10. Its native acceptance evidence is historical, recorded in
[Beta 10 qualification](BETA10-VALIDATION.md) and the
[creation report](reports/document-creation-20260930/README.md); no new live-font
test or installed-runtime replacement is claimed for Beta 11.

## Release gates

The 50 focused release-identity, build, documentation and synchronization tests
passed during preparation. The full local release gate passed: 2,492 Python tests (two skips, five
warnings), all 222 desktop tests, deterministic payloads, both private runtimes,
the website build and source/package checks. Developer ID signing verified 94 native binaries and 47 bundles, plus the
separately bundled Beztrace engine. Both signed runtimes passed offline startup,
HTTP/stdio catalogs, packaged installer CLI and MCP App checks; their bytes match
the final stapled payload. Apple accepted payload, app and DMG submissions.
Tickets are stapled and verified; Gatekeeper accepts the app and DMG. Sparkle
archive and feed signatures verify. The guarded publisher reran the full gate
and verified nested signatures,
signature-preserving install copies, the extracted ZIP and checksums, then
verified uploaded digests before publishing. Fresh unauthenticated downloads
matched all four local assets; Sparkle archive/feed signatures verify. See
[distribution evidence](reports/beta11-release-candidate/README.md).

## Remaining acceptance limits

Physical Intel/minimum-macOS testing, the exact signed older-to-Beta-11 desktop
update/component-migration trial, and narrow-window/dark-mode visual acceptance
remain unperformed. Automated runtime checks cover both bundled architectures
on the maintainer's Apple silicon Mac, including x86_64 through Rosetta.
The carried-forward group-pair native UI Undo issue and exact-pair card visual
acceptance are documented in [Beta 8 qualification](BETA8-VALIDATION.md).
The independent Beztrace Glyphs plugin's native qualification and signed release
remain separate. Its bundled engine is a development preview from a recorded
dirty source tree; signing does not establish tracing quality or plugin acceptance.

The user explicitly requested publication of Beta 11. These limits are
disclosed in the release notes. Full automated checks and signed-distribution
verification must pass before publication.

## Distribution

[Beta 11/build 53](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.11)
is published as a signed and notarized non-Latest prerelease. Signed tag
`v2.0.0-beta.11` identifies `d89068ee`. All four public downloads match the
verified local assets. The exact signed beta appcast is updated after public
archive verification. Beta 10 tags, assets and qualification records remain
preserved. Stable Latest remains v1.11.1. See the distribution evidence for
public download and branch verification results.

The public raw beta feed and registry match committed source, and the raw feed
signature verifies; see `public-branch-verification.json` in the distribution
evidence. The published documentation builds successfully.
