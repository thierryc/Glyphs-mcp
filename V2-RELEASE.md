# Glyphs MCP 2.0.0 — build 55

Glyphs MCP v2 connects AI clients to Glyphs 4 through a native bridge and separate
local server. The desktop companion guides installation, agent connections,
server controls and saved-font projects.

## Changes

- Thirteen tools with explicit document, glyph, master and layer targeting.
- Conversation previews, Apply, Keep without saving, Save and recovery actions.
- Font creation, scoped widths/spacing/kerning/outlines, compile/export preparation
  and native scripts within the connected bridge's advertised capabilities.
- Local checkpoints and Visual/Unified/Split source comparisons; two optional
  inspectors, eleven managed skills, guided Glyphs Python setup and Welcome.
- Stable Beztrace 0.1.1 engine included. Its independent Glyphs plugin is a
  separate installation, with signed/notarized build15 qualification.

## Install

Download [Glyphs-MCP-2.0.0.dmg](https://github.com/thierryc/Glyphs-mcp/releases/download/v2.0.0/Glyphs-MCP-2.0.0.dmg).
Install official Glyphs 4 first, launch with a license or Continue Trial, install
Python through Plugin Manager, select the **(Glyphs)** framework in Addons, then
save your work and quit Glyphs before installing components through Setup.
Glyphs 3 uses the separate [v1.11.0 release](https://github.com/thierryc/Glyphs-mcp/releases/tag/v1.11.0).

## Qualification and limits

The exact source passed 2,573 Python and 233 desktop tests. Signed/notarized
build 55 passed fresh install, width apply/discard/save, actual signed53→55 desktop
update and rejection cases, 54→55 component migration/failure/rollback/retry and
v1 migration on **macOS 14.6.1 arm64, Glyphs 4.1.1/build 4108, official Python 3.14.6**.
Claude Desktop 2.19675.0 read calls passed. These results are reused for unchanged
bytes, with public downloads/feed checked during promotion.

Declared minimum is macOS 14.0. Exact 14.0/current-macOS native qualification,
physical Intel execution, full VoiceOver/visual Reduce Motion, human language/
new-user review and live Codex/Claude Code smoke remain unverified. Cursor VM
live testing was waived based on reported host success. Glyphs 3 preservation
used a fixture, not a live coexistence run. See the [full qualification summary](https://thierryc.github.io/Glyphs-mcp/docs/v2/reference/release-qualification).

## Recovery

Keep leaves edits unsaved. Typed Undo refuses conflicting later changes.
Script/checkpoint Restore replaces later unsaved edits throughout the font and
clears native history; script recovery does not undo external file/network effects.
For an uncertain operation, check its result and current state rather than rerunning
it. A failed update/migration retains recovery evidence; never replace distributed
bytes in place. Report exact app, OS, Glyphs/client versions and redacted diagnostics.
