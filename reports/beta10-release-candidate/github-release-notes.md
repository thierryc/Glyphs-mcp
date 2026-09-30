Glyphs MCP 2.0.0 Beta 10 (build 52) adds new-font creation and improves checkpoint comparison.

- Create an empty font directly through `create_document`, with one Regular master and instance, configurable UPM and native IDs. Duplicate requests reuse the same document. Save separately through `save_document` as `.glyphs` or `.glyphspackage`.
- Thirteen public MCP tools and eleven synchronized managed skills, with new creation guidance.
- Checkpoint history discovers project fonts, offers Open/Open all in Glyphs, marks latest/reference versions and uses green/pink comparisons.
- The desktop app includes the universal Beztrace 0.1.1-dev.4 development engine with provenance, licenses and checksums. The separate Glyphs plugin remains outside Install All.

Requirements: macOS 14 or later, Apple silicon or Intel, and Glyphs 4 with Python (Glyphs) selected in Settings → Addons. Glyphs 3 remains on its separate pinned v1 release.

The complete local gate passed 2,492 Python tests (two skips) and 222 desktop tests, deterministic builds, both private runtimes and the documentation build. Both signed private runtimes passed packaged startup and HTTP/stdio checks. The desktop app, nested code and disk image are Developer ID signed and notarized; Gatekeeper, nested signatures, installed copies and Sparkle signatures verified. Creation, duplicate reuse, master reads, saving and native reopening passed on Glyphs 4.1.1/build 4108; detached native checks also passed on 4.1/build 4107.

Known qualification limits: physical Intel/minimum-macOS testing, the exact signed older-to-Beta-10 update/component-migration trial, narrow-window/dark-mode review and carried-forward group-pair native UI Undo/pair-card visual acceptance remain incomplete. Use the workflow recovery action before Keep/Save when reviewing group-pair kerning edits. Beztrace is a development engine from a recorded dirty source tree; the independent Glyphs plugin's native qualification and signed release are pending.

This prerelease does not replace Stable Latest. Download the versioned DMG and verify it against SHA256SUMS. The ZIP and signed appcast support beta desktop updates.
