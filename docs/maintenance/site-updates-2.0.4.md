# Website refresh for Glyphs MCP 2.0.4

Prepared 12 October 2026. This is ready-to-use editorial copy and implementation direction; the external websites have not been edited by this repository update.

## Canonical links

- [Signed macOS download](https://github.com/thierryc/Glyphs-mcp/releases/download/v2.0.4/Glyphs-MCP-2.0.4.dmg)
- [2.0.4 release notes](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.4)
- [Current documentation](https://thierryc.github.io/Glyphs-mcp/docs/v2/)
- [Installation guide](https://thierryc.github.io/Glyphs-mcp/docs/v2/getting-started/installation)
- [Qualification and limits](https://thierryc.github.io/Glyphs-mcp/docs/v2/reference/release-qualification)
- [Public source](https://github.com/thierryc/Glyphs-mcp)
- [Issue tracker](https://github.com/thierryc/Glyphs-mcp/issues)
- [Separate Glyphs 3 release](https://github.com/thierryc/Glyphs-mcp/releases/tag/v1.11.0)

For an evergreen button use GitHub's latest release page; a button labelled 2.0.4 should point to the exact versioned disk image. Keep the existing page URLs so inbound links continue to work.

## Anotherplanet project page

Target: https://www.anotherplanet.io/Glyphs-App-MCP-Server

The existing page describes an early command-line installation and v0.3 tools. Replace that material with the current desktop workflow. Correct the expansion of MCP to **Model Context Protocol**. Remove the private-access instruction and obsolete Node/Python proxy recipes from the primary guide; keep historical Glyphs 3 information behind a clearly labelled legacy link. Link to the maintained tool reference instead of duplicating signatures.

### Suggested title and description

**Title:** Glyphs MCP — AI-assisted font work in Glyphs 4

**Description:** An open-source desktop companion connecting Glyphs 4 to AI assistants, with native font editing, review and recovery. Download the signed macOS app.

### Replacement page copy

# Glyphs MCP

A design experiment in working with AI while keeping the font, the craft and the decisions in your hands.

Glyphs MCP connects Glyphs 4 to Codex, Claude, Cursor and other compatible AI applications through the Model Context Protocol. Ask an assistant to inspect a font, investigate spacing, prepare kerning changes, write a Glyphs script or produce font exports. Review the results in Glyphs and decide when to save.

The macOS desktop companion handles setup, local server controls and supported agent connections. A small native bridge accesses the open font; the separate server prepares supported jobs. Curve Inspector and Reference Inspector provide optional visual tools inside Glyphs.

## Start with a small task

1. Install Glyphs 4 and Python from its official Plugin Manager, then relaunch Glyphs.
2. Download the signed and notarized Glyphs MCP app and open Setup. If you have multiple Glyphs 4 copies, select the one you use and check its detected Python.
3. Install the components, connect your AI application and try a small task on a disposable font.

Already-authorized script edits can run without saving first. Preview requests wait for review. Script recovery restores the complete pre-run font state within the current Glyphs session; keeping an edit and saving the document are separate actions.

## What changed in 2.0.4

Setup recognizes the default Glyphs Python even when no framework setting has been saved. It shows which application and Python it detected, and offers an application selector only when several Glyphs 4 copies are found. A failed readiness check offers Install anyway with an explanation; it does not replace the Python module required for scripting.

Font export verification now uses the bundled private runtime, so FontTools does not need to be added to Glyphs Python. More detailed installation logs help identify application selection and Python loading failures.

Glyphs MCP 2.0.4/build 61 is signed and notarized for macOS 14 or later. The current desktop distribution is for Glyphs 4. Glyphs 3 has a separate retained 1.11.0 release. Read the qualification notes before relying on a particular platform or export workflow.

The project is open source. Share a reproducible issue, describe a useful workflow or contribute an improvement on GitHub.

**Buttons:** Download 2.0.4 · Read the guide · Source and feedback

### Portfolio card

**Glyphs MCP**

An open-source companion for AI-assisted font work in Glyphs 4. Explore, script and edit in conversation while keeping review, recovery and saving under your control.

## AP.CX Creative Foundry experiment

Target: https://ap.cx/tools/glyphs-mcp/

Retain its experiment/tool framing, but update the title, download, release label and metadata from 2.0.0 to 2.0.4/build 61. Replace the thirteen-tool count with twenty tools; retain eleven managed skills. Update the Python prerequisite to explain default detection. Replace obligatory source-review wording with the actual distinction between an authorized edit and a preview request. Link platform claims to qualification.

### Suggested title and description

**Title:** Glyphs MCP 2.0.4 for Glyphs 4 — AI-assisted font editing | AP.CX

**Description:** Connect Glyphs 4 to Codex, Claude and Cursor with a signed macOS companion, twenty MCP tools, native editing and private-runtime font export verification.

### Replacement page copy

# Glyphs MCP 2.0.4

Open-source Glyphs 4 desktop companion and MCP server.

Part of the AP.CX Creative Foundry experiments: tools that make type design more conversational while preserving the designer's decisions and native font workflow.

Keep your font open in Glyphs 4 and work with your AI assistant. Inspect glyphs and masters, prepare spacing and kerning changes, develop native scripts, compare fonts and stage exports. Twenty MCP tools coordinate document access, jobs, editing workflows and explicit saves; eleven managed skills guide supported agent workflows.

## From setup to a working session

Install official Glyphs 4 and its Python module through Plugin Manager. Relaunch Glyphs, save your work and quit normally before installing components. Open Glyphs MCP.app and use Setup to install the bridge, local server and optional inspectors, then configure Codex, Claude Code, Claude Desktop or Cursor.

Setup displays the detected Python for the chosen Glyphs application. When multiple Glyphs 4 copies are found, it lets you choose the copy you actually use. The server includes its own Python and dependencies; no terminal package installation is required for the sidecar.

## Designed for review and recovery

An authorized edit can run without a forced Save. A preview request waits for review. Keep changes without saving, save when authorized, or use the recovery offered for that workflow. Native scripts use a complete pre-run memory snapshot; restoring it also removes later unsaved changes and is limited to the current Glyphs session. Begin with a disposable font and a small change.

## The 2.0.4 update

- Detects the default Glyphs Python without requiring a saved framework preference.
- Shows detected application and Python information, with a selector when multiple Glyphs 4 copies are present.
- Provides an explained Install anyway option when readiness cannot be confirmed.
- Verifies font exports with private FontTools/HarfBuzz dependencies.
- Adds useful application, preference and Python details to installation logs.

## Availability and tested scope

The universal 2.0.4/build 61 app is Developer ID-signed, notarized and stapled. It targets macOS 14+ and Glyphs 4. Glyphs 3 uses the separate pinned 1.11.0 distribution.

The final source gate passed 2,952 Python tests and 263 desktop tests. Signed VM checks on Apple silicon/macOS 26.6.2 passed installation, default Glyphs Python detection, six static TTF/OTF and web-font export combinations, and live bridge/sidecar checks. Earlier core qualification includes macOS 14.6.1. Exact macOS 14.0 and physical Intel execution have not been qualified; Rosetta runtime startup is a separate check. Optional components retain their own requirements and evidence.

Read the release qualification for the full scope and remaining limits. Source and feedback are public on GitHub under Apache 2.0.

**Buttons:** Download 2.0.4 for macOS · Documentation · Release notes · GitHub

### Tools/experiment index card

**Glyphs MCP**

Open-source Glyphs 4 desktop companion and MCP server. Connect your AI assistant, prepare native font edits and review the result. Signed macOS app with setup, recovery and font export verification.

## Publishing checklist

- Replace the obsolete sections and update page titles, descriptions, structured data and social preview text.
- Update the Anotherplanet portfolio card and AP.CX Tools/Creative Foundry experiment card; keep their links pointing to the existing detailed pages.
- Use current Setup and font-workflow screenshots. Include the multiple-copy selector only in a genuine multiple-copy example; avoid images of legacy terminal installation.
- Test the download, documentation and legacy Glyphs 3 links on mobile and desktop.
- Keep future release facts in the maintained documentation. Avoid making the portfolio page a second technical manual.
