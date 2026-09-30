# Beta 10 qualification — build 52

Date: 2026-09-30. Branch: `lit/v2-beta`.
Product: `2.0.0`; release: `2.0.0-beta.10`.

## Scope

New `create_document` opens an empty unsaved native Glyphs font with a Regular
master and instance, configurable UPM, stable native IDs and duplicate protection.
The existing `save_document` saves the new document in either supported format.
The catalog now contains thirteen tools and eleven synchronized managed skills.

Desktop checkpoint history discovers saved project fonts, offers Open/Open all
in Glyphs, marks latest/reference versions and uses green/pink comparison colors.
The app bundles the universal Beztrace 0.1.1-dev.4 development engine and its
provenance, checksums, licenses and SBOMs. Its source distribution retains its
development provenance; the release copy is signed and notarized with the host.
The independent Glyphs plugin remains separate and excluded from Install All.

## Native verification

Creation, duplicate request reuse, master reads and verified Save As passed on
Glyphs 4.1.1/build 4108. Saved `.glyphs` and `.glyphspackage` files reopened through
the native reader with native IDs preserved. Earlier detached construction and
serialization checks passed on Glyphs 4.1/build 4107. See the dated
[creation and installation evidence](reports/document-creation-20260930/README.md).

The local desktop app and scoped MCP runtime were installed with backups and
their running identities verified. Live qualification used two owned disposable
documents; no edit or save was issued against the existing user font in those
checks. That font's dirty flag and generation remained unchanged during them.

## Release gates

The full local release gate passed: 2,492 Python tests (two skips, five warnings)
and all 222 desktop tests. Deterministic payloads, both private runtimes, eleven
synchronized skills, thirteen tools, the website build and metadata checks passed.
The initial run found a stale desktop assertion expecting twelve tools; it was
corrected and the complete gate passed. Earlier desktop Python fixtures and a
stale release-skill reference were also corrected with focused verification.
Developer ID signing verified 94 Mach-O files and 47 nested bundles, plus the
separately bundled Beztrace engine. The payload notarization passed and tickets were stapled and verified. Both
signed private runtimes passed startup, HTTP/stdio catalogs, packaged installer
and MCP App resource checks. App and DMG notarization passed; all three submissions were accepted.
Stapling, Gatekeeper, nested signatures, signature-preserving install copies,
extracted ZIP and checksum verification passed. Sparkle archive and feed
signatures verified. The guarded publisher reran the full gate successfully and published the four
assets as a non-Latest prerelease. Fresh unauthenticated downloads matched local
bytes and Sparkle archive/feed signatures verified. Stable Latest remains v1.11.1. Evidence is in [the distribution report](reports/beta10-release-candidate/README.md).

## Remaining acceptance limits

Physical Intel/minimum-macOS testing, the exact signed older-to-Beta-10 desktop
update/component-migration trial, and narrow-window/dark-mode visual acceptance
remain unperformed. Both bundled architectures are checked on the maintainer's
Apple silicon Mac, including x86_64 execution through Rosetta.
The carried-forward group-pair native UI Undo issue and exact-pair card visual
acceptance are documented in [Beta 8 qualification](BETA8-VALIDATION.md).
The independent Beztrace Glyphs plugin's native qualification and signed release
remain separate. Its engine is a development preview from a recorded dirty source
tree; bundling/signing does not establish tracing quality or plugin acceptance.

The user explicitly requested committing all changes and publishing Beta 10.
These limits are disclosed in the release notes; full automated checks and
signed-distribution verification must pass before publication.

## Distribution

[Beta 10/build 52](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.10)
is a published signed and notarized prerelease. Signed tag `v2.0.0-beta.10`
identifies `e1e71ef8`. The user authorized committing all changes and publication.
See `github-published.json` and `public-download-verification.json` in the
[distribution evidence](reports/beta10-release-candidate/README.md).
The exact signed beta appcast is published on the beta branch after public
archive verification. Public raw feed and registry bytes match committed source,
and the raw feed signature verifies; see `public-branch-verification.json`. No previous beta asset/tag or stable release was changed.
