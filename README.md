# Glyphs MCP Desktop 2.0.0

**2.0.0 · desktop build 55 · Glyphs 4.** Download the [signed and notarized disk image](https://github.com/thierryc/Glyphs-mcp/releases/download/v2.0.0/Glyphs-MCP-2.0.0.dmg), read the [release notes and qualification](V2-RELEASE.md), or follow the [v2 installation guide](https://thierryc.github.io/Glyphs-mcp/docs/v2/getting-started/installation).

The [thirteen-tool contract](content/reference/command-set.mdx) adds font creation through `create_document`; `save_document` persists the resulting open font. Native signed build 55 testing covers macOS 14.6.1 Apple silicon and Glyphs 4.1.1/build 4108. Declared macOS 14.0 and current-macOS native acceptance remain unverified; physical Intel testing is deferred.

Glyphs MCP connects AI applications to Glyphs 4 through a small native bridge
and a separate MCP server. The installer includes its private Python runtime;
no terminal setup is required for the Glyphs 4 sidecar. Install official Glyphs 4
first and launch it in trial mode or with your license. Install Python through
Glyphs' Plugin Manager and select the **(Glyphs)** framework in Addons before
installing the MCP components.

Open **Glyphs MCP.app** and use **Setup**. **Install All** reconciles Glyphs MCP,
Curve Inspector and Reference Inspector, then configures Codex, Claude Code,
Claude Desktop and Cursor. Bundled component cards also support independent install,
update, removal and retry. Upgrades preserve ports, startup settings and
unrelated agent configuration.

Setup also introduces **Beztrace**, an independent Glyphs image-tracing plugin,
with requirements, its independently signed build 15 release and setup guidance. The app bundles
the universal stable 0.1.1 engine; the Glyphs plugin remains separate. See [Beztrace setup](BETA.md#beztrace).

The permanent app includes Setup and Project destinations, a static menu-bar
popover, a dedicated troubleshooting-log window, local and public templates,
and a Git diff browser with opt-in font checkpoints. Its
native file tree opens source diffs in unified or split form and can compare
individual `.glyphspackage` glyphs as visual overlays or source text. Automatic
update checks are enabled by default and can be disabled in Settings. Desktop
launch at login is a separate opt-in setting.

In Glyphs, **Edit → Glyphs MCP Server…** opens Start/Stop and port settings.
The compact extension panel displays the project and bridge versions and
"Ready". Its heart button reopens Glyphs' nonmodal Welcome/support panel with
documentation, issue and support links.

The local v2 desktop companion adds a six-slide introduction covering
control, connections, prerequisites, v2 changes and community support. It appears
on first interactive launch and can be replayed through **File → Welcome & Support**
or the sidebar. **Skip to setup** and **Start setup** open Setup. Desktop login
launch stays quiet. See [local qualification and remaining manual checks](V2-RELEASE.md).

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
Results offer **Keep changes without saving**, **Save font**, and recovery.
Typed **Undo these changes** covers the recorded edit; script **Restore saved
version** reloads the whole font, replacing later unsaved edits and clearing Undo.
Keep ends wrapper recovery without saving and preserves native Undo/Redo.
`accept_job` verifies affected targets and saves the whole document when authorized.
Spacing proposals and
reference display ignore differences of at most 0.001 font units. Exact
native history and recovery keep the original values without rounding.

The thirteen tools are `get_status`, `list_documents`, `create_document`, `read_entities`,
`start_job`, `get_job`, `apply_job`, `accept_job`, `discard_job`, and
`save_document`, `start_edit_workflow`, `get_edit_workflow`, and
`respond_edit_workflow`. The shared MCP App supports preparation, saving and
review where the host supports interactive Apps; every action also works in
text. **Save and continue** saves existing work once and resumes the request.
The resulting edit remains unsaved until separately authorized. Cards reuse
matching Script details, and typed results show their intended change. Exact
source stays optional; fresh server checks still guard actions. See
[conversation edits](content/tutorial/conversation-edits.mdx).
See [installation](content/getting-started/installation.mdx) and the
[Glyphs 4 contract](content/reference/command-set-v2.mdx).

The v2 source targets Glyphs 4 only. Glyphs 3 remains available through the
separate pinned v1.11.0 release and its existing dependency setup. The two
documentation tracks describe these versions separately. V2 is available
as a signed and notarized
[GitHub release](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0).

Documentation sources: [v2 · 2.0.0](content/glyphs-mcp.md) and
[v1 · 1.11.0](website/versioned_docs/version-1.11.0/glyphs-mcp.md).
Beta 7 qualification and publication are recorded in [BETA7-VALIDATION.md](BETA7-VALIDATION.md).
Historical Beta 6 evidence remains in [BETA6-VALIDATION.md](BETA6-VALIDATION.md).
Beta 5 qualification is recorded in
[BETA5-VALIDATION.md](BETA5-VALIDATION.md); the published Beta 4 record remains
in [BETA4-VALIDATION.md](BETA4-VALIDATION.md).
The local site build has a version selector; existing v1 URLs stay at `/docs/`,
and v2 is configured at `/docs/v2/`. Both are built together from `website/`.
See [release qualification](V2-RELEASE.md) for current results and limits.
Historical beta evidence remains in [BETA.md](BETA.md).
Compatibility repository guide: [Glyphs 3 / 1.11.0](legacy/glyphs3/README.md).

For contributors, use [CODEX.md](CODEX.md) and the local packaging instructions
in [macos-installer/README.md](macos-installer/README.md). The stable disk image is `Glyphs-MCP-2.0.0.dmg`. See [release qualification](V2-RELEASE.md).
Stable releases retain `Glyphs-MCP-latest.dmg`. Historical beta releases remain on `lit/v2-beta` with a separate feed.

Author: Thierry Charbonnel. [Documentation](https://ap.cx/gmcp),
[Issues](https://github.com/thierryc/Glyphs-mcp/issues),
[Support](https://github.com/sponsors/thierryc).

New stable versions appear on [GitHub Releases](https://github.com/thierryc/Glyphs-mcp/releases/latest). Use **Check for Updates** in the desktop app to check on demand; beta builds use a separate beta feed. Releases are built, signed and notarized locally; no GitHub Actions are used for release publishing.


Private lean v2 qualification is indexed in [reports/README.md](reports/README.md).
The latest RV02 follow-up covers the installed OpenType, precision and native API
guidance. Native Python uses the advertised `python_script` job and
`script.native.v1` without adding tools. Preparation never executes code. An
ordinary task authorizes Run without a separate source review; previews wait.
Clean saved fonts need no extra Save, while dirty fonts require authorized saving.
Restore saved version reloads the whole baseline and replaces later unsaved edits.
Successful edit cards offer a 30-second countdown to Keep changes without
saving, ending the workflow recovery offer. Typed Keep preserves native Undo/Redo. Say **“wait for my answer”** to disable it.
See [script execution and recovery](skills/glyphs/references/python-scripts.md).

Beta 8 development removes the native-script 4,096-surface ceiling while retaining
the complete 4 MiB request budget. Large selectors use incremental read-only
preparation, one saved baseline and one result workflow. Typed edit and read
limits are unchanged. Qualification is tracked in [the milestone plan](BETA8-MILESTONES.md).

### Local font checkpoints (Beta 8 candidate)

The opt-in project setting records exact saved baselines and authorized MCP saves
as font-scoped Git checkpoints. Keep stays unsaved; failed checkpoints can be
retried without another Save. Bounded history, recorded actions, comparison and
whole-font historical reload share the existing thirteen tools and app project UI.
See [checkpoint workflow](skills/glyphs/references/git-checkpoints.md).
See the [milestone 6 qualification report](reports/beta8-milestone6/README.md) for
installed editor/app checks, measured costs and remaining limits.
