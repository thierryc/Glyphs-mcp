# Codex identity and activity feedback

This feature is included in the local **2.5.0/build 72** source candidate on
`lit/codex-identity-feedback`. The published 2.4.0 release retains its original
qualification scope; these changes have not been published as an app update.

## Connection identity

The Codex plugin already declares the Glyphs MCP composer icon and listing logo.
The sidecar and stdio proxy also advertise that same PNG through standard MCP
`serverInfo.icons`, as a data URI, with the product website. The icon is available
offline and is advertised once per server initialization, rather than copied
onto every tool descriptor. Its bytes match `plugins/glyphs-mcp/assets/icon.png`;
the build test enforces that correspondence for the packaged sidecar asset.

Codex 0.165.0-alpha.1.2 resolves a same-named standalone MCP entry ahead of a
plugin entry. An isolated app-server qualification confirmed:

| Registration | Reported plugin attribution | Server icon available |
| --- | --- | --- |
| Standalone | None | Yes |
| Plugin only | `glyphs-mcp@glyphs-mcp` | Yes |
| Both | None | Yes |

Native setup reads Codex's effective MCP configuration through its CLI. When a
matching enabled connection already exists through the plugin, setup reuses it
without adding a shadowing standalone entry. Detection includes the CLI bundled
with current Codex/ChatGPT desktop hosts when a separate shell install is absent.
Older clients without usable CLI discovery retain standalone setup.

Discovery distinguishes an absent connection from a disabled, conflicting or
ambiguous one. Such conflicts are held for review. Setup also rechecks the
configuration after asynchronous discovery and refuses to overwrite intervening
manual edits.

Existing matching standalone settings remain byte-identical, including custom
timeouts. Different endpoints and explicitly disabled entries are preserved and
reported for review in Codex settings. Setup does not automatically delete legacy
entries whose ownership cannot be established. To recover plugin attribution for
an existing duplicate, review and remove that standalone entry in Codex settings.
The server-advertised icon remains available to clients using standalone setup.

The native app does not remove a plugin-owned connection. Its Remove action
directs the user to Codex settings. This keeps plugin removal and its
skills under the client's existing ownership controls.

## Activity feedback

The existing optional `show_edit_workflow` card remains the live display. Data
tools continue to return ordinary text and structured state without opening a
card on every read. The four workflow tools now have readable titles and short
invocation labels. Only the display tool links to a UI resource; it also provides
the optional OpenAI template compatibility alias.

Workflow results and model context contain a compact `progress` projection:
workflow/job identity, state, activity status, phase label, completed/total counts
when known, the count unit, indeterminate status and the recorded update time.
It is derived from the existing workflow and native operation evidence. It does
not add a store, change revisions/tokens, execute work or close recovery.

- Per-target scripts show completed callbacks, not a count of verified edits.
- Whole-script invocations use an indeterminate bar, with no invented percentage
  or ETA. They cannot be safely preempted while Python is executing.
- A complete callback count does not prove cleanup, saving or verification has
  finished. The projection distinguishes the finishing phase.
- Failed/cancelled scripts retain partial counts and their original warnings.
- Counts from another blocking job are not displayed as this workflow's progress.
- Save, Restore, Keep and Automatic Keep retain their existing authorization and
  recovery behavior. Visible progress never dispatches an action by itself.

The card retains its visibility-aware refresh policy, identity checks, stale/error
handling and opt-in script details. Its measured bar and last-update time use the
same state returned to text clients.

## Request-scoped notifications

The workflow tool wrapper reports progress only when its request lasts longer
than one second and its client provides a progress token. It emits a starting
message and the resulting workflow phase, without a numeric total. Fast reads
stay quiet. Reporting failures do not fail or retry the underlying operation;
each notification has a half-second timeout so an unresponsive receiver cannot
hold up the operation result indefinitely.
Cancellation stops reporting; it does not pretend to interrupt native Python.

The request context is never retained for an asynchronous job after the tool
returns. Workflow cards and normal polling provide feedback between calls.
Glyphs application workflows are not MCP protocol task-augmented requests.

The tested Codex app server supplies a progress token, but its direct
`mcpServer/tool/call` endpoint did not forward progress events to the test client.
The standard notifications are verified with an MCP client; their exact visual
presentation in Codex remains host-dependent. Use the workflow card for live job
feedback. A server notification does not create an assistant conversation message.

The collapsed card is compact: a small font-name header with a Details toggle,
one status/count row, and a 3-pixel progress bar. The request, exact path, target
inventory and update time stay in Details. Necessary action buttons are 28 pixels
high; warnings and recovery consequences remain visible. The host receives the
card's compact content height rather than a fixed preview height.

## Qualification

Run the font-free Codex qualification with the locked runtime:

```sh
python3 scripts/qualify_codex_feedback.py \
  --python build/private-runtime/arm64/bin/python3
```

It installs a minimal fixture plugin into disposable Codex homes, starts ephemeral
test threads without starting model turns, and exercises the actual sidecar
registration, logo and workflow projection. It never connects to Glyphs or changes
the user's Codex configuration. Results and logs go to
`build/codex-feedback-qualification/`.

The locked runtime uses FastMCP 2.12.0 and MCP SDK 1.29.1. FastMCP does not expose
server icons in its constructor, so `presentation.configure_identity` is the
small compatibility boundary around the SDK's native identity fields. Developer
environments using older SDKs retain plugin branding without server icon fields.

The focused Python suite covers metadata through both server and stdio proxy,
context injection, progress projection, slow/fast requests, notification failure,
UI transitions, script cancellation/recovery and deterministic packaging. Native
tests cover effective CLI discovery, plugin reuse, custom/disabled settings,
quoted TOML sections and cancellation before configuration writes. Browser review
covers light/dark presentation, whole scripts and narrow partial-failure states.

The completion run passed **3,327 Python tests** (four environment/optional
skips) and **325 native desktop tests**. A separate run of the 23 feedback
tests against the checksum-pinned runtime passed without skips, including
the server/proxy icon fields unavailable in the older development SDK.
The locked-runtime Codex
app-server qualification passed all three registration modes and retained its
report under `build/codex-feedback-2.5.0-qualification/`. Browser review verified
light/dark measured and whole-script states and 300-pixel result/partial-failure
cards with readable recovery controls. All fixtures are font-free.

The fresh unsigned local app at `dist/local/Glyphs MCP.app` passed its build
receipt and separate bundle verification as 2.5.0/build 72. Its identity and
remaining distribution gates are recorded in `V2.5.0-PREPARATION.md`.

These checks qualify source and a local candidate. They do not install it, reload
the user's MCP connection, or certify a conversation-detail screenshot from the
running release. Exact Codex icon placement and optional invocation labels must
be checked after an explicitly authorized candidate installation/reload.
