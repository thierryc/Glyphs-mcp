# Glyphs MCP 2.0.0 Beta 6

**Beta 6/build 48 is published as a signed and notarized GitHub prerelease.
Its signed desktop update and component migration passed in VirtualBuddy.
Stable Latest remains v1.11.1.**

Beta 6 adds per-master Dimensions reference reads and guarded edits, plus a
shared conversation workflow for preparing, applying, saving and discarding
font changes. The interface exposes twelve tools and eleven managed skills.
Claude's text save follow-ups retain their workflow reference; reopened cards
refresh their state before enabling actions and tolerate host permission delays.
**Save and continue** saves existing work once and resumes the requested edit;
the resulting changes remain unsaved until a separate save.

The published identity is `2.0.0-beta.6`, desktop build 48, on `lit/v2-beta`.
Exact qualification and artifact evidence is in
[BETA6-VALIDATION.md](BETA6-VALIDATION.md). Historical Beta 5 evidence remains in
[BETA5-VALIDATION.md](BETA5-VALIDATION.md).

Glyphs 3 is not included in the Beta 6 desktop payload. Its separate v1.11.0
release, source metadata and documentation remain unchanged.

## Requirements and availability

Beta 6 targets macOS 14 or later, Apple silicon and Intel, and Glyphs 4. The
installer bundles architecture-matched private runtimes; terminal setup is not
required for an end-user installation. Glyphs still needs its own **Python
(Glyphs)** scripting environment selected under **Glyphs → Settings → Addons**.

Download the signed and notarized
[Beta 6 disk image](https://github.com/thierryc/Glyphs-mcp/releases/download/v2.0.0-beta.6/Glyphs-MCP-2.0.0-beta.6.dmg)
from the [Beta 6 prerelease](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.6).
Its SHA-256 is
`578c7d9f362826dd7da6cc21118d35c8684ef2ab09f6bf231f7723685dc81ac1`.
Beta 6 remains a prerelease rather than the repository's Stable Latest.

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
   Undo/Redo before an authorized `accept_job`.

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

## Help test Beta 6

Signed update and component migration passed on an Apple-silicon VirtualBuddy
guest. The remaining manual matrix covers fresh, partial, removal, ownership
conflict, running-Glyphs, absent-agent and reload-required scenarios, physical
Intel, and all four agent connections after reload or restart. Do not mark
those rows complete without evidence from the exact candidate.

Useful reports include the beta/build number, macOS and processor, Glyphs
version/build, affected card, operation state, client, exact reproduction and a
redacted diagnostic report. Share a disposable font only when it can be public.
[Report a beta issue](https://github.com/thierryc/Glyphs-mcp/issues/new?title=%5BBeta%202.0.0%5D%20&body=Beta%20and%20build%3A%0AmacOS%20and%20processor%3A%0AGlyphs%20version%3A%0AAI%20client%3A%0ASteps%3A%0AExpected%3A%0AActual%3A).

Known limitations: the welcome screen remains a placeholder; the twelve-tool
workflow is intentionally narrower than v1 and exposes no arbitrary Python
tool. In Project visual diffs, changing glyph files can retain the previously
selected master even when that master is unchanged; choose a layer without the
“unchanged” suffix to display the available geometry difference. Physical
Intel acceptance and the complete packaged manual scenario matrix remain
unverified. Exact build-48 signed application update and component migration
evidence is recorded in [BETA6-VALIDATION.md](BETA6-VALIDATION.md); Beta 4
results are not carried forward.
