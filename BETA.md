# Glyphs MCP 2.0.0 Beta

> Historical Beta guidance: the local checkout now prepares unpublished
> 2.0.0/build 55. Beta 12/build 54 evidence remains preserved; the public
> download and signed Beta feed still target Beta 11/build 53. See the
> [current release checklist](V2-RELEASE-CHECKLIST.md).

**Beta 12/build 54 (`2.0.0-beta.12`) is an unpublished local candidate.**
Unsigned builds and scoped native qualification exist; no signed public Beta 12
distribution is available.
Beta 11/build 53 remains the published signed and notarized prerelease.
Stable Latest remains v1.11.1. See [Beta 12 preparation](BETA12-VALIDATION.md).

Beta 12 began as metadata preparation. Authorized follow-ups add group-pair
native Undo routing, guided official Python setup, a six-slide desktop Welcome,
and installer/localization fixes. Local qualification and remaining release
gates are recorded in [the v2 checklist](V2-RELEASE-CHECKLIST.md).
It retains Beta 10's new-font creation with `create_document`, duplicate-safe retries
and native master/instance IDs. Save separately using `save_document` as
`.glyphs` or `.glyphspackage`. It ships thirteen public tools and eleven managed
skills. Checkpoint history now discovers project fonts, opens selected/all fonts
in Glyphs, marks the latest/reference versions and uses green/pink comparisons.
The current source bundles the universal stable Beztrace 0.1.1 engine;
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

The source target is `2.0.0-beta.12`, desktop build 54, on `lit/v2-beta`.
The published identity remains `2.0.0-beta.11`, desktop build 53.
See [qualification](BETA11-VALIDATION.md) and the
[release report](reports/beta11-release-candidate/README.md).

## Requirements and availability

Beta 12 targets macOS 14 or later, Apple silicon and Intel, and Glyphs 4. The
installer bundles architecture-matched private runtimes; terminal setup is not
required for end-user installation. Install official Glyphs 4 first and open it
in trial mode or with your license. Glyphs needs its own **Python (Glyphs)**
environment installed through **Window → Plugin Manager → Modules** and explicitly
selected under **Glyphs → Settings → Addons**. Restart after module installation,
select the **(Glyphs)** framework, then quit normally before component installation.
The local Beta 12 companion can open the official Python module page and check
the selected runtime; these new controls are not part of the published Beta 11 app.
Physical Intel qualification remains deferred; the scoped VM tests use Sonoma
14.6.1 on arm64 and do not establish the exact 14.0 minimum.
Glyphs 3 remains on its separate pinned v1.11.0 release.

Download the signed and notarized
[Beta 11 disk image](https://github.com/thierryc/Glyphs-mcp/releases/download/v2.0.0-beta.11/Glyphs-MCP-2.0.0-beta.11.dmg)
from the [Beta 11 prerelease](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.11).
Verify it against the release's `SHA256SUMS` file.
Beta 11 remains a prerelease and does not replace Stable Latest.

## First session

1. Complete Glyphs 4 and Python setup above. Make a duplicate of a font for
   testing, save current work and quit Glyphs normally.
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

## Welcome in the local Beta 12 companion

The six-slide introduction appears on first interactive launch. Replay it with
**File → Welcome & Support** or the sidebar; use **Skip to setup** or **Start setup**
to reach Setup. Normal completed relaunches and desktop login do not reopen it.
Glyphs' heart button separately opens the native Welcome/support links panel.

## Qualification and remaining checks

The local Beta 12 bridge passes the wider group-pair native Undo/Redo matrix;
the companion passes scoped setup/recovery, Claude card visuals, scripts/saving,
localized layouts, keyboard navigation and quiet login checks in Sonoma 14.6.1.
See [the candidate-specific checklist](V2-RELEASE-CHECKLIST.md) for evidence and
boundaries. These are not signed final-artifact results or retroactive Beta 11 fixes.

Exact signed update/component migration, macOS 14.0, final distribution and
stable Beztrace integration remain pending. Full VoiceOver, visual Reduce Motion
and other human checks are [deferred to the maintainer](V2-MANUAL-TESTS-TODO.md).
Physical Intel remains deferred. Only Claude live calls were in the VM scope;
configuration fixtures do not prove every client's live behavior.

Useful reports include the beta/build number, macOS and processor, Glyphs
version/build, affected card, operation state, client, exact reproduction and a
redacted diagnostic report. Share a disposable font only when it can be public.
[Report a beta issue](https://github.com/thierryc/Glyphs-mcp/issues/new?title=%5BBeta%202.0.0%5D%20&body=Beta%20and%20build%3A%0AmacOS%20and%20processor%3A%0AGlyphs%20version%3A%0AAI%20client%3A%0ASteps%3A%0AExpected%3A%0AActual%3A).

Known limitations: native Python
uses the existing job tools and saved-version recovery; use the installed
connection’s advertised capabilities. In Project visual diffs, changing glyph
files can retain the previously selected master even when it is unchanged;
choose a layer without the “unchanged” suffix to display the available geometry
difference. Native unnamed-node null-to-empty normalization is a separate
selective-recovery follow-up. Historical build-48 update/migration evidence is
in [BETA6-VALIDATION.md](BETA6-VALIDATION.md).

## Beztrace

Beta 12 Setup includes **Beztrace**, an independent Glyphs plugin for tracing
PNG/JPEG images into editable paths. Current source guidance links to the
[official 0.1.0/build 15 plugin release](https://github.com/thierryc/beztrace/releases/tag/glyphs-v0.1.0)
and identifies the bundled universal stable 0.1.1 engine. The companion has its
own Developer ID signature and accepted Apple notarization. Native qualification
covers macOS 14.6.1 arm64, Glyphs 4.1.1/build 4108 trial and official Python 3.14.6.
Intel native execution is untested; physical Intel MCP testing stays deferred.
Final signed MCP integration and screenshots remain separate gates.

Install All manages the three bundled MCP components and agent connections; it
does not install the independent Beztrace plugin. Availability does not establish
that Glyphs has loaded it. Older installed Beta builds can still show earlier
source links and labels. Historical Beta 11 includes 0.1.1-dev.4; its original
bytes and evidence remain unchanged.

Beztrace declares Glyphs 4.1/build 4107 or later and Python 3.9 or later in Glyphs;
that compatibility declaration is broader than the tested environment above.
Follow the [frozen build 15 source guide](https://github.com/thierryc/beztrace/blob/dbd7a696afda9a215c8e8a4aa42315cd799116f9/Companions/Glyphs/README.md),
install separately and relaunch Glyphs. Use **Path → Beztrace…**. The plugin works
without the MCP server. Select the compatible stable engine explicitly with
**⋯ → Choose Engine…**; a source-linked plugin may otherwise prefer its preserved
development engine. The separate
[stable 0.1.1 engine release](https://github.com/thierryc/beztrace/releases/tag/v0.1.1)
remains unchanged. See [qualified-input verification](reports/v2-release-readiness/m33-qualified-build15-20261005/report.md)
for exact package, signing, native and lifecycle evidence.
