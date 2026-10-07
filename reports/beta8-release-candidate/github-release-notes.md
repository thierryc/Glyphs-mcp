# Glyphs MCP 2.0.0 Beta 8 · build 50

Beta 8 integrates font checkpoint history into the comparison workspace and adds exact kerning edits and language-based proof pairs. It also reduces repeated preparation, polling and connection work across native edit workflows.

## What changed

- **Integrated checkpoints:** a compact picker groups saved checkpoints by date, with readable titles and local times. Selecting a checkpoint compares it with the latest saved checkpoint in the existing text/glyph viewer. Restore and Action details use separate sheets; Working changes returns to the previous file selection.
- **Opt-in font history:** verified MCP saves can create local Git checkpoints with recorded action evidence. Historical restoration replaces the open font's content, including unsaved changes, clears Undo, and does not save. Checkpoint comparisons use saved revisions and exclude unsaved font edits.
- **Exact kerning edits:** set or remove explicit glyph/group pairs in LTR, RTL and vertical directions, preserving fractional values and the distinction between zero and a missing entry. Selective workflow recovery remains available before Keep/Save.
- **Language proofing:** inspect bounded candidate pairs from a pinned MIT-licensed dataset covering 24 language tags. Proofing reports existing coverage; it does not prescribe kerning values.
- **Native workflow improvements:** remove the 4,096-surface script ceiling while retaining the request byte budget, prepare small edits from their actual scope, perform cleanup incrementally, and reduce repeated status/details work.
- Keep twelve public tools, eleven managed skills, and the existing Keep, Save and recovery controls.

## Install

Requires **macOS 14 or later and Glyphs 4**. The app is universal for Apple silicon and Intel and includes architecture-specific private runtimes. Glyphs 3 remains on its separate [v1.11.0 release](https://github.com/thierryc/Glyphs-mcp/releases/tag/v1.11.0).

Download `Glyphs-MCP-2.0.0-beta.8.dmg`, drag **Glyphs MCP.app** into Applications, then use **Setup** to update components. Save your work before any requested Glyphs restart. Begin beta testing with a copy of a font.

## Verification and known limitations

- The complete local gate passed **2,464 Python tests** (two skips) and **219 desktop tests**. Both installed font formats passed **36 kerning lifecycle cases each**.
- The installed checkpoint picker, empty comparison, glyph comparison, action-details sheet, restore confirmation/cancel, and return to working changes were checked.
- **Group-pair native Undo remains unresolved:** the tested group-pair value did not change through Glyphs' ordinary Undo menu. Use the workflow's **Undo these changes** before Keep/Save when reviewing such edits; Keep ends that selective recovery offer. Glyph-pair native Undo/Redo passed.
- Visual acceptance of the new exact-pair result card and this release's signed desktop-update/component-migration trial remain incomplete. Earlier beta acceptance does not establish these checks for Beta 8.
- Physical Intel, minimum-macOS and the complete manual client/failure matrix remain open. A universal build does not establish every hardware/OS combination.

See [Beta 8 validation](https://github.com/thierryc/Glyphs-mcp/blob/v2.0.0/BETA8-VALIDATION.md) and [the beta guide](https://github.com/thierryc/Glyphs-mcp/blob/v2.0.0/BETA.md). Please include the beta/build number, macOS, processor, Glyphs version, AI client and reproduction steps in issue reports.

This is a prerelease. Stable Latest remains v1.11.1.
