# Glyphs MCP Desktop 2.0.0 Beta 4

**Beta preparation — not yet available for public download.**
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
update checks and desktop launch at login are separate opt-in settings.

In Glyphs, **Edit → Glyphs MCP Server…** opens Start/Stop and port settings.
The compact extension panel displays the project and bridge versions and
"Ready". Its heart button reopens a placeholder welcome window.
That window appears automatically once; its final design is in progress.

Prepare supported spacing, kerning, slant and start-node jobs, review their
reports, then apply the stored result. Native Save accepts it; native Undo/Redo
or whole-job discard keeps experimentation reversible. Spacing proposals and
reference display ignore differences of at most 0.001 font units. Exact
native history and recovery keep the original values without rounding.

The seven tools are `get_status`, `list_documents`, `read_entities`,
`start_job`, `get_job`, `apply_job`, and `discard_job`.
See [installation](content/getting-started/installation.mdx) and the
[Glyphs 4 contract](content/reference/command-set-v2.mdx).

The Beta 4 payload is Glyphs 4-only. Glyphs 3 remains available through the
separate pinned v1.11.0 release and its existing dependency setup. The two
documentation tracks describe these versions separately. This candidate is
prepared locally; it has not been published as a release.

Documentation sources: [v2 · 2.0.0 Beta 4](content/glyphs-mcp.md) and
[v1 · 1.11.0](website/versioned_docs/version-1.11.0/glyphs-mcp.md).
Beta 4 qualification is pending; the published Beta 3 record remains in
[BETA3-VALIDATION.md](BETA3-VALIDATION.md).
The site has a version selector; existing v1 URLs stay at `/docs/`, and v2 uses
`/docs/v2/`. Both are built together from `website/`.
Compatibility repository guide: [Glyphs 3 / 1.11.0](legacy/glyphs3/README.md).

For contributors, use [CODEX.md](CODEX.md) and the local packaging instructions
in [macos-installer/README.md](macos-installer/README.md). Beta artifacts, when released, use `Glyphs-MCP-2.0.0-beta.4.dmg`.
Stable releases retain `Glyphs-MCP-latest.dmg`. The beta stays on `lit/v2-beta`
and does not replace the stable download.

Author: Thierry Charbonnel. [Documentation](https://ap.cx/gmcp),
[Issues](https://github.com/thierryc/Glyphs-mcp/issues),
[Support](https://github.com/sponsors/thierryc).

New stable versions appear on [GitHub Releases](https://github.com/thierryc/Glyphs-mcp/releases/latest). Use **Check for Updates** in the desktop app to check on demand; beta builds use a separate beta feed. Releases are built, signed and notarized locally; no GitHub Actions are used for release publishing.


Private lean v2 qualification is indexed in [reports/README.md](reports/README.md).
The latest RV02 follow-up covers the installed OpenType, precision and native API
guidance. Native scripts use Glyphs execution routes; they add no MCP tool.
