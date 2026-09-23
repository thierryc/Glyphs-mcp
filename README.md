# Glyphs MCP Desktop 2.0.0 Beta 6

**Beta 6 available — release `2.0.0-beta.6`, desktop build 48.**
The signed and notarized GitHub prerelease is ready to download.
See the [beta guide](BETA.md) and [release and launch plan](BETA-LAUNCH.md).

Glyphs MCP connects AI applications to Glyphs 4 through a small native bridge
and a separate MCP server. The installer includes its private Python runtime;
no terminal setup is required for the Glyphs 4 sidecar.

Open **Glyphs MCP.app** and use **Setup**. **Install All** reconciles Glyphs MCP,
Curve Inspector and Reference Inspector, then configures Codex, Claude Code,
Claude Desktop and Cursor. Every card also supports independent install,
update, removal and retry. Upgrades preserve ports, startup settings and
unrelated agent configuration.

The permanent app includes Setup and Project destinations, a static menu-bar
popover, a dedicated troubleshooting-log window, local and public templates,
and a read-only Git diff browser. Its
native file tree opens source diffs in unified or split form and can compare
individual `.glyphspackage` glyphs as visual overlays or source text. Automatic
update checks are enabled by default and can be disabled in Settings. Desktop
launch at login is a separate opt-in setting.

In Glyphs, **Edit → Glyphs MCP Server…** opens Start/Stop and port settings.
The compact extension panel displays the project and bridge versions and
"Ready". Its heart button reopens a placeholder welcome window.
That window appears automatically once; its final design is in progress.

Prepare supported spacing, kerning, slant, start-node, outline and negotiated
closed native-action jobs; run feature compiler diagnostics; or stage verified
static, variable and web-font exports. Conversation edits apply complete results
under the original request; previews, warnings and incomplete coverage wait for
review. Artifact publication remains separately authorized.
`accept_job` verifies the affected live
targets, saves the whole document and closes the rollback window; native Undo/Redo
or whole-job discard keeps an unaccepted experiment reversible. Spacing proposals and
reference display ignore differences of at most 0.001 font units. Exact
native history and recovery keep the original values without rounding.

The twelve tools are `get_status`, `list_documents`, `read_entities`,
`start_job`, `get_job`, `apply_job`, `accept_job`, `discard_job`, and
`save_document`, `start_edit_workflow`, `get_edit_workflow`, and
`respond_edit_workflow`. The shared MCP App supports preparation, saving and
review where the host supports interactive Apps; every action also works in
text. **Save and continue** saves existing work once and resumes the request.
The resulting edit remains unsaved until separately authorized. See
[conversation edits](content/tutorial/conversation-edits.mdx).
See [installation](content/getting-started/installation.mdx) and the
[Glyphs 4 contract](content/reference/command-set-v2.mdx).

The Beta 6 payload is Glyphs 4-only. Glyphs 3 remains available through the
separate pinned v1.11.0 release and its existing dependency setup. The two
documentation tracks describe these versions separately. Beta 6 is available
as a signed and notarized
[GitHub prerelease](https://github.com/thierryc/Glyphs-mcp/releases/tag/v2.0.0-beta.6).

Documentation sources: [v2 · 2.0.0 Beta 6](content/glyphs-mcp.md) and
[v1 · 1.11.0](website/versioned_docs/version-1.11.0/glyphs-mcp.md).
Beta 6 qualification and publication are recorded in [BETA6-VALIDATION.md](BETA6-VALIDATION.md).
Beta 5 qualification is recorded in
[BETA5-VALIDATION.md](BETA5-VALIDATION.md); the published Beta 4 record remains
in [BETA4-VALIDATION.md](BETA4-VALIDATION.md).
The site has a version selector; existing v1 URLs stay at `/docs/`, and v2 uses
`/docs/v2/`. Both are built together from `website/`.
Compatibility repository guide: [Glyphs 3 / 1.11.0](legacy/glyphs3/README.md).

For contributors, use [CODEX.md](CODEX.md) and the local packaging instructions
in [macos-installer/README.md](macos-installer/README.md). Beta artifacts use `Glyphs-MCP-2.0.0-beta.6.dmg`.
Stable releases retain `Glyphs-MCP-latest.dmg`. The beta stays on `lit/v2-beta`
and does not replace the stable download.

Author: Thierry Charbonnel. [Documentation](https://ap.cx/gmcp),
[Issues](https://github.com/thierryc/Glyphs-mcp/issues),
[Support](https://github.com/sponsors/thierryc).

New stable versions appear on [GitHub Releases](https://github.com/thierryc/Glyphs-mcp/releases/latest). Use **Check for Updates** in the desktop app to check on demand; beta builds use a separate beta feed. Releases are built, signed and notarized locally; no GitHub Actions are used for release publishing.


Private lean v2 qualification is indexed in [reports/README.md](reports/README.md).
The latest RV02 follow-up covers the installed OpenType, precision and native API
guidance. Native scripts use Glyphs execution routes; they add no MCP tool.
