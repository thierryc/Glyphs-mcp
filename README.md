# Glyphs MCP Desktop 2.5.0

**Stable · desktop build 73 · Glyphs 4.** [Download 2.5.0](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.5.0). Path Doctor adds profile-preserving path diagnosis and qualified seam repair, with measured Pen-point cleanup guidance, safer Codex setup and compact progress feedback.

The server status stays visible in the top-right toolbar across views. Native outline recovery preserves readable metadata alongside stroke profiles and attributes.

See the [2.5.0 qualification record](V2.5.0-RELEASE.md) for signed artifacts, checks and retained limits. Prior [2.4.0 qualification](V2.4.0-RELEASE.md) keeps its original scope.

The [twenty-one data/action tools and optional card-display tool](content/reference/command-set.mdx) includes font creation, native source opening, UFO/OTF/TTF import, window activation and closing with explicit save/discard handling. The save-free Edit-tab opening and unsaved `duplicate_document` copies introduced in 2.0.3 remain available; update the bridge and sidecar together through Setup. `save_document` persists an explicitly identified font.

Glyphs MCP connects AI applications to Glyphs 4 through a small native bridge
and a separate MCP server. The installer includes its private Python runtime;
no terminal setup is required for the Glyphs 4 sidecar. Install official Glyphs 4
first and launch it in trial mode or with your license. Install Python through
Glyphs' Plugin Manager, then relaunch Glyphs. Setup detects the default module
even when Glyphs has not saved a framework preference. If you use a custom
Python, select it in Glyphs' Settings → Addons. Setup displays the detected
Python for the selected application and offers a copy selector only when
multiple Glyphs 4 applications are detected.

Open **Glyphs MCP.app** and use **Setup**. **Install All** reconciles Glyphs MCP,
Curve Inspector and Reference Inspector, then configures Codex, Claude Code,
Claude Desktop and Cursor. Bundled component cards also support independent install,
update, removal and retry. Upgrades preserve ports, startup settings and
unrelated agent configuration.

Setup offers **Beztrace** engine 0.2.1 and companion 0.2.0/build 25 for Apple Silicon on macOS 26.6.2 or later. Choose the engine manually in Beztrace; independent installations, engines and settings are protected. Beztrace stays outside Install All. See [Beztrace setup](content/workflows/beztrace.mdx).

Diffenator is deferred to a future release and removed from Setup. No Diffenator runtime is distributed in 2.3.0.

The permanent app includes Setup, Tasks and Project destinations, a native menu-bar
menu, a dedicated troubleshooting-log window, local and public templates,
and a Git diff browser with opt-in font checkpoints. The
project's **Diff / Config** control keeps Diff as the full-height default and
groups font sources, settings and external-tool actions in Config. Saved
`.glyphs` sources offer **Create Package Copy…** with source preservation and
native verification; see [font package copies](macos-installer/README.md#font-package-copies-in-projects).
The native file tree opens source diffs in unified or split form and can compare
individual `.glyphspackage` glyphs as visual overlays or source text. PNG, JPEG and WebP diffs use Before / Both / After, a draggable divider and shared zoom controls. [Tasks](docs/companion-tasks.md) shows open workflows and blockers, conversation handoff and guarded recovery for abandoned work. Automatic
update checks are enabled by default and can be disabled in Settings. Desktop
launch at login is a separate opt-in setting.

In Glyphs, **Edit → Glyphs MCP Server…** opens Start/Stop and port settings.
The compact extension panel displays the project version and
"Ready". Its heart button reopens Glyphs' nonmodal Welcome/support panel with
documentation, issue and support links.

The v2 desktop companion includes a six-slide introduction covering
control, connections, prerequisites, v2 changes and community support. It appears
on first interactive launch and can be replayed through **File → Welcome & Support**
or the sidebar. **Skip to setup** and **Start setup** open Setup. Desktop login
launch stays quiet. See [qualification and remaining manual checks](V2-RELEASE.md).

Prepare supported spacing, kerning, slant, start-node, outline and negotiated
closed native-action jobs; run feature compiler diagnostics; or stage verified
static, variable and web-font exports. Conversation edits apply complete results
under the original request; previews, warnings and incomplete coverage wait for
review. Artifact publication remains separately authorized.

Exact kerning assignments use `kerning_edit`: 1–100 glyph/group pairs with
explicit masters and directions, fractional values, and distinct set/remove
operations. Native preparation avoids a font copy and worker startup while
retaining selective recovery. Read-only language proofing offers bounded pairs
to inspect from a pinned MIT dataset; it does not suggest values or launch
collision analysis. See the [kerning guidance](skills/glyphs-mcp-kerning/SKILL.md).
Results offer **Keep**, **Save**, and recovery, with consequences visible beneath the controls. Keep closes the task without saving; Save saves the whole font, including other unsaved edits. Both end the temporary recovery option.
Typed **Undo these changes** covers the recorded edit; script **Restore** restores the complete pre-run memory copy, replacing later unsaved edits
and clearing Undo. It preserves edits made before Run; recovery lasts for the
current Glyphs session.
Keep ends wrapper recovery without saving and preserves native Undo/Redo.
`accept_job` verifies affected targets and saves the whole document when authorized.
Spacing proposals and
reference display ignore differences of at most 0.001 font units. Exact
native history and recovery keep the original values without rounding.

The twenty-one data/action tools are `get_status`, `list_tasks`, `list_documents`, `create_document`, `duplicate_document`, `open_document`, `import_document`,
`activate_document`, `open_edit_tab`, `close_document`, `read_entities`,
`start_job`, `compare_fonts`, `get_job`, `apply_job`, `accept_job`, `discard_job`, and
`save_document`, `start_edit_workflow`, `get_edit_workflow`, and
`respond_edit_workflow`. The additional display-only `show_edit_workflow` opens
an optional MCP App when a visual preview, substantial report, live controls or
recovery information adds value. Routine progress, success and errors stay in
native chat; unresolved decisions and missing information prefer the host's
native question tool, grouping related independent questions. Ordinary chat is
the fallback. Disable Automatic Keep before waiting on a native answer; silence,
Skip and dismissal apply no choice.
Every action also works in text. Scripts can run on clean, dirty or pathless fonts without saving.
The resulting edit remains unsaved until separately authorized. Cards reuse
matching Script details, and typed results show their intended change. Exact
source stays optional; fresh server checks still guard actions. See
[conversation edits](content/tutorial/conversation-edits.mdx).
The [conversation UI guide](docs/conversation-ui-directives.md) maps use cases to
native questions, conversation feedback and optional cards, including current
renderer limits.
See [installation](content/getting-started/installation.mdx) and the
[Glyphs 4 contract](content/reference/command-set-v2.mdx).

The v2 source targets Glyphs 4 only. Glyphs 3 remains available through the
separate pinned v1.11.0 release and its existing dependency setup. The two
documentation tracks describe these versions separately. V2 is available
as a signed and notarized
[GitHub release](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.5.0).

Documentation sources: [v2 · 2.5.0](content/glyphs-mcp.md) and
[v1 · 1.11.0](website/versioned_docs/version-1.11.0/glyphs-mcp.md).
The local site build has a version selector; existing v1 URLs stay at `/docs/`,
and v2 is configured at `/docs/v2/`. Both are built together from `website/`.
See [2.3.0 qualification](V2.3.0-RELEASE.md) and [2.2.0 qualification](V2.2.0-RELEASE.md) for their separate results and limits.
Historical beta reports remain in [the qualification archive](reports/README.md);
the original beta guides and plans are preserved in the [v2.0.0 source tag](https://github.com/thierryc/Glyphs-mcp/tree/v2.0.0).
Compatibility repository guide: [Glyphs 3 / 1.11.0](legacy/glyphs3/README.md).

For contributors, use [CODEX.md](CODEX.md) and the local packaging instructions
in [macos-installer/README.md](macos-installer/README.md). The published disk image is `Glyphs-MCP-2.5.0.dmg`.
Stable releases retain `Glyphs-MCP-latest.dmg`. The separate `lit/v2-beta` feed delivers the published stable update to existing beta installations.

For the next development cycle, see [proposed priorities](docs/maintenance/next-evolution.md) and [Anotherplanet/AP.CX page updates](docs/maintenance/site-updates-2.0.4.md).

Author: Thierry Charbonnel. [Documentation](https://ap.cx/gmcp),
[Issues](https://github.com/thierryc/Glyphs-mcp/issues),
[Support](https://github.com/sponsors/thierryc).

New stable versions appear on [GitHub Releases](https://github.com/thierryc/Glyphs-mcp/releases/latest). Use **Check for Updates** in the desktop app to check on demand; beta builds use a separate beta feed. Releases are built, signed and notarized locally; no GitHub Actions are used for release publishing.


Historical lean v2 qualification is indexed in [reports/README.md](reports/README.md).
The RV02 follow-up covers the installed OpenType, precision and native API
guidance. Native Python uses the advertised `python_script` job and
`script.native.v1` without adding tools. Preparation never executes code. An
ordinary task authorizes Run without a separate source review; previews wait.
Dirty, clean and pathless fonts run without Save under `script.recovery.snapshot.v1`
and preparation version 3. Restore returns to a detached full-font copy,
including earlier unsaved edits; recovery is limited to the current Glyphs session.
With Automatic Keep enabled, a visible, connected and freshly reconciled
successful edit or script card offers a 30-second countdown to **Keep**,
leaving changes unsaved and ending the workflow recovery offer. Failed, partial, blocked and
uncertain outcomes and text-only interaction remain manual. Typed Keep preserves
native Undo/Redo. Say **“wait for my answer”** to disable the countdown; that
preference persists until changed.
See [script execution and recovery](skills/glyphs/references/python-scripts.md).

Native scripts have no 4,096-surface ceiling while retaining
the complete 4 MiB request budget. Large selectors use incremental read-only
preparation, one pre-run recovery copy and one result workflow. Typed edit and read
limits are unchanged. Qualification is tracked in [the V2 release notes](V2-RELEASE.md).

### Local font checkpoints

The opt-in project setting records exact saved baselines and authorized MCP saves
as font-scoped Git checkpoints. Keep stays unsaved; failed checkpoints can be
retried without another Save. Bounded history, recorded actions, comparison and
whole-font historical reload share the existing twenty-two tools and app project UI.
See [checkpoint workflow](skills/glyphs/references/git-checkpoints.md).
See the [milestone 6 qualification report](reports/beta8-milestone6/README.md) for
installed editor/app checks, measured costs and remaining limits.

## Upgrade to 2.1.0

1. Use **Check for Updates** or download the signed disk image above and replace the desktop app in Applications.
2. Save your work and quit all open Glyphs 4 copies normally.
3. Open **Setup**. If several Glyphs 4 copies appear, choose the one you actually use and check its detected Python. Update the bundled components together, or use **Install All** to reconcile components and connections.
4. Reopen that Glyphs copy and reload your configured AI application. Use `get_status` to confirm the loaded bridge and sidecar identities.

Existing ports, startup preferences and unrelated agent configuration are preserved. A failed Python readiness check offers **Install anyway** after an explicit warning. This permits component installation; it does not install Python or make an unavailable scripting environment work. Install the official module in Glyphs and relaunch to restore scripting. Export verification uses the server's private FontTools/HarfBuzz runtime.

For a failed setup, share the desktop troubleshooting log. It now records application paths and identities, preference domains, detected Python candidates and probe failures. Review it for personal paths before sharing. See the [installation guide](content/getting-started/installation.mdx) and [2.1.0 qualification](V2.1.0-RELEASE.md).

## Earlier 2.0.3 release

Already-authorized scripts run directly after preparation, with current-state
recovery and no forced Save. Preview requests still wait. Curve Inspector 0.5.2
explains no-change results, and the versioned agent package exposes its skills
digest. See [2.0.3 qualification](V2.0.3-RELEASE.md).

## Earlier 2.0.2 release

The 2.0.2 release introduced responsive initialization status and compiled-font comparison
through `compare_fonts`. Diffenator and Beztrace have optional managed Setup
cards; their downloads remain gated on independently signed and qualified
distributions. See [compiled comparisons](content/workflows/font-comparison.mdx)
and [2.0.2 qualification](V2.0.2-RELEASE.md).
