# Glyphs MCP 2.0.0 Beta

**Beta 11/build 53 (`2.0.0-beta.11`) is published as a signed and notarized prerelease.**
All four public downloads and Sparkle signatures are verified. Stable Latest remains v1.11.1.

Beta 11 advances release metadata and documentation with unchanged runtime behavior.
It retains Beta 10's new-font creation with `create_document`, duplicate-safe retries
and native master/instance IDs. Save separately using `save_document` as
`.glyphs` or `.glyphspackage`. It ships thirteen public tools and eleven managed
skills. Checkpoint history now discovers project fonts, opens selected/all fonts
in Glyphs, marks the latest/reference versions and uses green/pink comparisons.
The desktop app bundles the universal Beztrace 0.1.1-dev.4 development engine;
its independent Glyphs plugin remains outside Install All.
See [Beta 11 qualification](BETA11-VALIDATION.md).

Beta 9 adds a Beztrace companion card with plugin requirements and setup
guidance. Its separate development plugin is excluded from Install All.

Beta 8 introduced opt-in local font checkpoints and integrates history into the
existing comparison workspace. A compact picker shows readable titles and local
times; selecting a checkpoint compares it with the latest saved checkpoint.
Unsaved font edits are excluded. Restore and Action details open separate sheets.

It also adds exact glyph/group kerning assignments and removals in LTR, RTL and
vertical directions, plus bounded language-filtered proof pairs from a pinned
MIT-licensed dataset. Proofing reports coverage without suggesting kerning values.
The fixed 4,096-surface native-script ceiling is removed; the request byte budget,
exact targeting and saved-version recovery remain. Beta 10 extends the public surface to thirteen tools while retaining eleven
managed skills.

Finish an edit with **Keep changes without saving**, **Save font**, or its
recovery action. Typed **Undo these changes** covers the recorded edit and ends
when you Keep or Save. Script **Restore saved version** and historical checkpoint
restoration replace the whole open font, discard later unsaved edits, clear Undo,
and do not save; external effects are not restored. Saving requires authorization.
Visible connected successful result cards offer automatic Keep and **Wait for my
answer**. Text-only clients remain manual.

The published identity is `2.0.0-beta.11`, desktop build 53, on `lit/v2-beta`.
See [qualification](BETA11-VALIDATION.md) and the
[release report](reports/beta11-release-candidate/README.md).

## Requirements and availability

Beta 11 targets macOS 14 or later, Apple silicon and Intel, and Glyphs 4. The
installer bundles architecture-matched private runtimes; terminal setup is not
required for end-user installation. Glyphs still needs its own **Python
(Glyphs)** environment selected under **Glyphs → Settings → Addons**.
Glyphs 3 remains on its separate pinned v1.11.0 release.

Download the signed and notarized
[Beta 11 disk image](https://github.com/thierryc/Glyphs-mcp/releases/download/v2.0.0-beta.11/Glyphs-MCP-2.0.0-beta.11.dmg)
from the [Beta 11 prerelease](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.11).
Verify it against the release's `SHA256SUMS` file.
Beta 11 remains a prerelease and does not replace Stable Latest.

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

## Help test Beta 8

The group-pair native Undo check remains unresolved: the tested group-pair
value did not change through Glyphs' ordinary Undo menu. Use the workflow's
**Undo these changes** before Keep/Save when reviewing those edits. Glyph-pair
native Undo/Redo and 72 installed kerning lifecycle cases passed.

Visual acceptance of the new exact-pair result card and this release's signed
desktop-update/component-migration trial remain incomplete. Physical Intel,
minimum-macOS and the complete manual client/failure matrix also remain open.
Earlier beta acceptance does not establish these checks for Beta 8.

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

## Beztrace

Beta 11 Setup includes **Beztrace**, an independent Glyphs plugin for tracing
PNG/JPEG images into editable paths. The card identifies plugin 0.1.0/build 11
and the bundled universal 0.1.1-dev.4 development engine. The engine is signed
and notarized inside the distributed desktop app; both architectures passed
startup checks. Its recorded dirty source provenance, licenses and SBOMs are
included. These checks do not establish tracing quality or plugin acceptance.

The separate Glyphs plugin remains an unsigned development preview, with native
qualification and a signed plugin release pending. Install All manages the three
bundled MCP components and agent connections; it does not install the Beztrace
Glyphs plugin. Availability does not establish that Glyphs has loaded it.

Beztrace requires Glyphs 4.1/build 4107 or later and Python 3.9 or later in Glyphs.
After separate plugin setup and a Glyphs relaunch, use **Path → Trace Image…**.
The plugin works without the MCP server. See the card's setup documentation;
the separate [0.1.0 engine release](https://github.com/thierryc/beztrace/releases/tag/v0.1.0)
and [pinned integration reference](https://github.com/thierryc/beztrace/blob/45b1108fb7f51d5877c964a296a867412eb167cb/Companions/Glyphs/README.md)
remain available independently.
