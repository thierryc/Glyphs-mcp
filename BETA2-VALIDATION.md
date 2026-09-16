# 2.0.0 Beta 2 — local validation

Status on 16 September 2026: **2.0.0 Beta 2, build 44, is signed, notarized,
verified and published as a non-Latest GitHub prerelease.**

## Implemented candidate

- The project workspace uses a full-height native split view with a resizable,
  filtered and hierarchical changed-file browser on the left and one on-demand
  comparison on the right. A native sidebar list gives every nested folder and
  file an Xcode-style indentation level and disclosure control. Selection
  survives refresh when the file remains.
- Text comparisons use the pinned PierreDiffsSwift 1.2.4 package at commit
  `c2249d7890de957a96480711152d90a06fa1222b`, with unified/split layouts,
  wrapping, selection and copying. Editing, comments, annotations, staging and
  commit controls are absent.
- Glyph files under `.glyphspackage/glyphs/` add Visual/Text switching, layer
  selection and Before/Both/After overlays. Unchanged geometry remains neutral;
  current outlines remain near-black with lighter neutral nodes and handles,
  reference changes are mint, and the symmetric-difference fill is cyan.
  Ordered difference arrows, Reset, 25–3200%
  zoom, Glyphs keyboard shortcuts, pinch, Option-scroll and the temporary Z
  tool are available. Holding Space shows a pure-black silhouette, and canvas
  panning uses the final inverted direction. Both views retain their state
  during the application session.
- Git comparison semantics are combined `HEAD` to working tree. Added,
  untracked, deleted and renamed paths, detached HEAD and repositories without
  commits are covered without modifying the index, refs or working files.
- The visual worker uses Glyphs 4's authoritative decomposed geometry through
  the version-matched private runtime bundled with the app, with the installed
  runtime retained as a fallback. Its schema-2 JSON contract includes layers,
  paths, symmetric differences, changed segments, anchors, widths, metrics,
  ordered region bounds and changed-layer IDs. A missing or
  incompatible runtime falls back to Text with a readable explanation instead
  of leaving an empty canvas.
- Binary, non-UTF-8, symbolic-link and over-2-MiB sides are not rendered. Git
  helpers and mutable features are disabled. Both embedded web surfaces use
  nonpersistent storage, local generated content and blocked navigation. The
  SVG document forbids inline and remote scripts; a bundled isolated content
  script accepts only bounded read-only camera and presentation commands.

No public MCP tool, interface revision, bridge protocol, job kind or schema was
changed. Glyphs 3 remains pinned to 1.11.0.

## Automated qualification

The complete `scripts/run_local_release_tests.sh` passed with the repository's
`.venv-v2` Python interpreter:

- 1,929 Python tests passed and 2 optional tests skipped.
- All 189 macOS installer tests passed, including the expanded 19-test project
  suite for Git comparison, safety, hierarchy, glyph-layer pairing and package
  validation.
- ARM64 and Intel private runtimes started without downloads and exposed the
  unchanged seven-tool catalog over HTTP and the stdio proxy.
- Two independently generated installer payloads were byte-for-byte identical.
- The documentation production build, lean package validation, synchronized
  eleven-skill package, shell syntax and `git diff --check` passed.
- A fresh unsigned app build and candidate security verification passed. Its
  receipt records Pierre 1.2.4, the pinned commit, its resource bundle identity,
  and exact hashes for both bundled JavaScript resources.

After the delta and navigation correction, the focused desktop project suite
passed 18 of 18 tests, including schema-2 decoding and viewport math; the
geometry/worker suites passed 27 of 27 tests, and the desktop build/security
suite passed 18 of 18 tests. A fresh unsigned app build and receipt verification
passed again, and `git diff --check` remained clean.

The final local candidate also passed the complete suite after the Overview
scroll-width correction, explanatory animated diff-loading states, screen-stable
0.5-pixel neutral outlines, 0.65-pixel delta segments, 0.25-pixel node details,
the strengthened delta fill, and the persistent left origin guide. The designed
680 × 420 disk-image background and Finder layout are checked by the release
suite and remain editable from their committed SVG source.

The host has Xcode 26.3 and Apple Swift 6.2.4 rather than Xcode 16. The app and
all tests target macOS 14.0, the application remains in Swift language mode
5.9, and the pinned Pierre package builds in Swift 6 mode. An exact Xcode 16
build remains a distribution-matrix check if that compiler version is required
as a release claim.

## Native and visible checks

The worker was exercised through the app-bundled private `glyphs-cli` with
Glyphs 4 against both a generated `.glyphspackage` and the Dactylotype project.
The Dactylotype `A_breve.glyph` response contained non-empty authoritative
geometry for every master layer without opening or changing a user document.

The unsigned desktop app was launched against a repository with 171 changed
files. The visible check confirmed the resizable hierarchy, filter, branch and
count, status badges, initial selection, Pierre unified diff and layout/wrap
controls. Accessibility inspection identifies each file row with its complete
path and status. Selecting Dactylotype `A_breve.glyph` rendered the layer picker,
Before/Both/After overlay controls, guides, width delta, advance edges, nodes,
Bezier handles and anchors. The current outline remained near-black, controls
used lighter neutral grays, reference changes were mint and the geometric delta
fill was cyan. All four
ordered difference regions were visited without wrapping; the 567% accent and
743% foot regions remained visible, Reset restored 100% Fit, Command-plus and
Command-Option-zero produced 125% and actual-size 345%, and Visual/Text switching
preserved a 125% viewport.

The documentation screenshot is
`content/images/desktop-git-diff-beta2.png`.

## Signed distribution and remaining matrix work

Commit `42eb72b34955cf202c16a3b1e9a8044f75e074b2` was pushed only to
`lit/v2-beta`. The signed annotated tag `v2.0.0-beta.2` points to that commit;
`main` was not changed. Apple accepted the payload/components submission
`ae5ccf8b-9584-4f75-bdbb-067b4f5c6545`, the outer app submission
`818a33d8-0242-42e5-a5b3-2004e1aaca6b`, and the final restored DMG submission
`afd649b5-2919-4dc7-bf2e-b6950823f762`. After correcting Finder icon placement
without changing the signed app payload or tag, Apple accepted replacement DMG
submission `f594e3f0-abfc-4cd7-b07c-8775fb057c1c`. The app and corrected DMG
were stapled and accepted by Gatekeeper.

The final verifier checked 74 Mach-O files, 32 bundles, the mounted DMG and an
extracted installed copy. The publisher reran all local gates before upload,
then GitHub's asset digests were compared with the exact local files. The
[GitHub prerelease](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.2)
is published with `make_latest=false`; the stable Latest release remains
`v1.11.0`. Only the beta branch carries the signed Sparkle feed.

Final release checksums:

- `f65431f5a405442971b029022692f22e642477a3c376782b3e5a07fd25433443` — DMG
- `9af495f4e4d834088df8d99e6a14a6faa3ed5f87137217b2f35f963ea9e7e532` — Sparkle ZIP
- `a1b088f0cb8a533eb4a44b0507d9b2996b13c7cfc9459010596b3e42468bd61d` — signed appcast

The remaining evidence gap is environmental, not hidden: the final universal
bytes were automatically architecture-qualified, but were not exercised on a
physical Intel Mac. The final DMG passed local mounted and extracted-install
verification, but a second clean VirtualBuddy guest launch could not be run
because the installed VirtualBuddy build disables file transfer. The Sparkle
archive signature and update metadata passed verification; an end-to-end
in-app update from Beta 1 build 43 to Beta 2 build 44 is not recorded here.
The host used Xcode 26.3 and Swift 6.2.4 rather than an exact Xcode 16 install.
