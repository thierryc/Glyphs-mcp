# Glyphs MCP 2.0.0 Beta

**Beta 7/build 49 is published as a signed and notarized GitHub prerelease.
Stable Latest remains v1.11.1.** Development metadata has advanced to
[Beta 8/build 50](BETA8-VALIDATION.md); there is no Beta 8 build yet.

Beta 7 adds native Python scripting, unified edit results and faster native
preparation for selected typed edits. It retains twelve tools, eleven managed
skills and the 4,096 eligible-surface limit. Exact targets and a verified saved
baseline precede script execution; preparation and polling never run Python.

Finish an edit with **Keep changes without saving**, **Save font**, or its
recovery action. Typed **Undo these changes** covers the recorded edit.
Script **Restore saved version** reloads the whole font and discards later
unsaved edits; external effects are not restored. Visible, connected successful
result cards offer a 30-second automatic Keep countdown and **Wait for my
answer**. Text-only clients remain manual. Saving requires authorization;
**Save and continue** saves existing work once, then leaves the new edit unsaved.

The published identity is `2.0.0-beta.7`, desktop build 49, on `lit/v2-beta`.
See [qualification](BETA7-VALIDATION.md) and the
[release report](reports/beta7-release-20260927/README.md). The exact-release
signed desktop-update/component-migration test remains unperformed and is
explicitly disclosed; signing, notarization and public asset verification passed.
Beta 6’s earlier update test is historical evidence, not Beta 7 acceptance.

Glyphs 3 is not included in the Beta 7 desktop payload. Its separate v1.11.0
release, source metadata and documentation remain unchanged.

## Requirements and availability

Beta 7 targets macOS 14 or later, Apple silicon and Intel, and Glyphs 4. The
installer bundles architecture-matched private runtimes; terminal setup is not
required for an end-user installation. Glyphs still needs its own **Python
(Glyphs)** scripting environment selected under **Glyphs → Settings → Addons**.

Download the signed and notarized
[Beta 7 disk image](https://github.com/thierryc/Glyphs-mcp/releases/download/v2.0.0-beta.7/Glyphs-MCP-2.0.0-beta.7.dmg)
from the [Beta 7 prerelease](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.7).
Its SHA-256 is
`0bb76ec30f0edbdd9d1a439d3f87c3c6cadab0a278d460dd08522c18369cfa55`.
Beta 7 remains a prerelease rather than the repository's Stable Latest.

## First session

1. Make a duplicate of a font for testing and save current work in Glyphs.
2. Drag **Glyphs MCP.app** from the disk image to **Applications**, then open
   the installed copy.
3. In **Setup**, choose **Install All**. All three Glyphs components are handled
   in one transaction, followed by Codex, Claude Code, Claude Desktop and
   Cursor connections. Cards remain on Setup and show **Queued**,
   **Installing**, **Installed** or **Failed** as work progresses.
4. If Glyphs is running, use the inline **Quit Glyphs** guidance and complete
   its normal save prompts. Installation resumes only after it is safe to
   replace components.
5. Reopen or reload installed agent applications when their cards request it.
   Start the MCP server and verify the address shown in Setup, normally
   `http://127.0.0.1:9680/mcp/`.
6. In **Project**, create a disposable project, then exercise a small supported
   spacing or kerning job on the font copy. Review the report and verify native
   Undo/Redo, then choose Keep changes without saving, Save font, or recovery.

## Setup cards

The component cards manage **Glyphs MCP**, **Curve Inspector** and **Reference
Inspector**. Missing items offer **Install**. Installed items offer **Update**
and **Remove**. Failed work offers **Retry**. Individual removal requires
confirmation and preserves unrelated components and existing preferences.

The compact **Connections** cards manage:

- **Codex**: MCP configuration and managed skills.
- **Claude Code**: MCP configuration and managed skills.
- **Claude Desktop**: MCP configuration.
- **Cursor**: the complete local Glyphs MCP plugin bundle, including its MCP
  manifest, assets and skills.

**Install All** includes all four connections even when a host is not detected.
Configuration changes create backups, preserve unrelated entries and custom
options, and change only the Glyphs MCP entry. Cursor update and removal require
a verified installer-owned bundle; modified or unowned content is reported as
a conflict rather than overwritten or deleted.

## Troubleshooting logs

The discreet log button in the Setup header opens one reusable **Glyphs MCP
Logs** window. It combines bounded installation events, per-card failures,
recent server events, `sidecar.log` and `sidecar-error.log`. Advanced users can
filter and refresh sources, copy selected or all text, copy a redacted
diagnostic report, or reveal the log folder in Finder. Missing log files are
reported without failing the view. Tokens, credentials and authorization
headers are removed from copied diagnostics.

## Templates and updates

The beta uses `templates/registry.json` and the update feed on `lit/v2-beta`.
Template refresh is independent of component installation. Desktop updates and
component reconciliation are also separate operations; a migration failure
must leave the manager available to retry or continue with the previous
installation.

## Help test Beta 7

The signed desktop-update/component-migration test for this exact release
remains open. Installed visual card countdown/Details, physical Intel,
minimum-macOS, the complete manual client matrix and some fault-injection
cases also remain unqualified. Automated checks and installed text workflows
are separate evidence; do not mark manual rows complete without testing them.

Useful reports include the beta/build number, macOS and processor, Glyphs
version/build, affected card, operation state, client, exact reproduction and a
redacted diagnostic report. Share a disposable font only when it can be public.
[Report a beta issue](https://github.com/thierryc/Glyphs-mcp/issues/new?title=%5BBeta%202.0.0%5D%20&body=Beta%20and%20build%3A%0AmacOS%20and%20processor%3A%0AGlyphs%20version%3A%0AAI%20client%3A%0ASteps%3A%0AExpected%3A%0AActual%3A).

Known limitations: the welcome screen remains a placeholder. Native Python
uses the existing job tools and saved-version recovery; use the installed
connection’s advertised capabilities. In Project visual diffs, changing glyph
files can retain the previously selected master even when it is unchanged;
choose a layer without the “unchanged” suffix to display the available geometry
difference. Native unnamed-node null-to-empty normalization is a separate
selective-recovery follow-up. Historical build-48 update/migration evidence is
in [BETA6-VALIDATION.md](BETA6-VALIDATION.md).
