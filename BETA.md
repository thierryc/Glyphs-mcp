# Glyphs MCP 2.0.0 Beta 3

**Status: Beta 3 is published as a signed and notarized GitHub prerelease. The
stable Latest release remains v1.11.1.**

Beta 3 unifies installation, server controls and agent connections in a single
native **Setup** page for Glyphs 4. The source target is `2.0.0-beta.3`, desktop
build 45, on `lit/v2-beta`. Local qualification evidence and the remaining
manual matrix are recorded in [BETA3-VALIDATION.md](BETA3-VALIDATION.md).

Glyphs 3 is not included in the Beta 3 desktop payload. Its separate v1.11.0
release, source metadata and documentation remain unchanged.

## Requirements and availability

Beta 3 targets macOS 14 or later, Apple silicon and Intel, and Glyphs 4. The
installer bundles architecture-matched private runtimes; terminal setup is not
required for an end-user installation. Glyphs still needs its own **Python
(Glyphs)** scripting environment selected under **Glyphs → Settings → Addons**.

Download the signed and notarized
[Beta 3 disk image](https://github.com/thierryc/Glyphs-mcp/releases/download/v2.0.0-beta.3/Glyphs-MCP-2.0.0-beta.3.dmg),
or review the complete
[Beta 3 release](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.3),
including the signed Sparkle update archive, appcast and `SHA256SUMS`. Beta 3 is
deliberately not the repository's Latest release; stable v1.11.1 remains the
default stable download.

Published SHA-256 values:

```text
f3e7af3a8dd4262258689803bca17f4d9b0a5c823218198eb76f712150c15900  Glyphs-MCP-2.0.0-beta.3.dmg
17a94148ffc5de3b24fa7d16b4342b52e7310763f8b46547974bd43cdc1b2950  Glyphs-MCP-2.0.0-beta.3.zip
c82e535612f2e954ba4158aa1e99c1abbd2c4b2f87ed6bb1db4fb54e3548239e  appcast.xml
```

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
   Undo/Redo before Save.

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

## Help test the candidate

The remaining manual matrix covers fresh, partial, update, removal, ownership
conflict, running-Glyphs, absent-agent and reload-required scenarios on Apple
silicon and Intel. It also verifies all four agent connections after reload or
restart. Do not mark those rows complete without evidence from the exact
candidate.

Useful reports include the beta/build number, macOS and processor, Glyphs
version/build, affected card, operation state, client, exact reproduction and a
redacted diagnostic report. Share a disposable font only when it can be public.
[Report a beta issue](https://github.com/thierryc/Glyphs-mcp/issues/new?title=%5BBeta%202.0.0%5D%20&body=Beta%20and%20build%3A%0AmacOS%20and%20processor%3A%0AGlyphs%20version%3A%0AAI%20client%3A%0ASteps%3A%0AExpected%3A%0AActual%3A).

Known limitations: the welcome screen remains a placeholder; the seven-tool
workflow is intentionally narrower than v1 and exposes no arbitrary Python
tool. In Project visual diffs, changing glyph files can retain the previously
selected master even when that master is unchanged; choose a layer without the
“unchanged” suffix to display the available geometry difference. Physical Intel
acceptance, signed-update migration and the complete packaged manual scenario
matrix remain unverified. Developer ID signatures, Apple notarization,
stapling, Gatekeeper acceptance, DMG extraction, published asset identity and
the signed Sparkle feed are verified for the released candidate.
