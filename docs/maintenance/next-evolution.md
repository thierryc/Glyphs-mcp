# Next evolution of Glyphs MCP

## Next-version to-do

- [x] Qualify automatic Glyphs MCP setup for Antigravity App 2.31.1 and Antigravity IDE 2.6.0. [Issue #67](https://github.com/thierryc/Glyphs-mcp/issues/67)

### Antigravity desktop acceptance

The development connector is under **AI Agents**. When either desktop app is detected, **Install All** includes Antigravity once. The card shows MCP configuration and global skills separately. **Retry** repeats the requested operation and can complete a partial setup.

- Both clients target the shared `~/.gemini/config/mcp_config.json` and `~/.gemini/config/skills/`. On the development Mac, the legacy MCP config is a symlink to the shared config, and Antigravity App shows the existing `glyphs-mcp-server` connection. Setup preserves a matching entry with custom settings and uses `glyphs-mcp` with `serverUrl` for a fresh connection. [MCP configuration](https://antigravity.google/docs/mcp) · [Global skill discovery](https://antigravity.google/docs/customization-discovery/)
- Setup backs up the config before changing it. **Update** can move an owned connection to the active port. Review a disabled, conflicting or malformed config before retrying the MCP step. **Uninstall** preserves modified and unowned entries and skill copies, including links to external skills.
- Use a separate macOS account or disposable VM with both apps signed in, a working Glyphs MCP installation and a disposable font. Check that the test account has no Claude installation or preinstalled Glyphs skills. Run Setup once. For each app, verify one Glyphs MCP entry, inspect its tool catalog, call `get_status` and `list_documents`, then observe the agent loading an installed Glyphs skill. Record whether each app reloads automatically or needs a refresh or restart.
- Repeat with a matching manual `glyphs-mcp-server` entry with fixture headers and an older installer-owned skill. Verify the manual config stays byte-identical, the owned skill updates, and removal preserves the manual connection and any local skill edits. Both apps need live evidence before the next release claims support.

On Glyphs-November (macOS 26.6.2, Glyphs 4.1.1 build 4108), the development companion showed one Antigravity card for both apps. Fresh setup in the tester profile installed one connection on port 9680 and 12 managed skills. The profile had no Claude installation or preinstalled Glyphs skills.

- **Fresh setup.** On first launch after setup, App 2.31.1 and IDE 2.6.0 each showed one healthy `glyphs-mcp` server with 22 tools and the global `/glyphs` skill in **Customizations → Installed**. In the IDE, open **Customizations** from the agent pane sidebar. Each client read the installed `glyphs/SKILL.md`, called `get_status` and `list_documents`, and reported a reachable bridge and the same disposable font.
- **Update.** The companion replaced an installer-owned v2.6.0 Glyphs skill, preserved the manually configured `glyphs-mcp-server` entry and its custom header byte for byte, and kept the legacy symlink. Both clients still showed the old entry while open. After fully quitting and reopening both clients, **Customizations → Installed** showed one healthy `glyphs-mcp-server` server with 22 tools in each client. Both loaded the upgraded skill and repeated the two calls successfully. The guest App auto-updated to 2.31.2 on relaunch and also passed the alias check. The App 2.31.1 upgrade check was repeated from the original signed build.
- **Uninstall.** The companion preserved the manual config byte for byte and retained a locally modified skill while removing the 11 unmodified managed skills. After reinstalling the managed skills, the tester profile was restored to the original single-server setup. A final MCP probe confirmed the bridge was reachable, the disposable font was clean, and its SHA-256 matched the pre-test copy.

The baseline is published **2.0.4/build 61**, with twenty tools and eleven managed skills. [Release qualification](../../V2.0.4-RELEASE.md) and [publication evidence](../../reports/2.0.4-build61-published.md) describe what was tested. New source documentation and optional development material do not alter the signed release or its tag.

## Earlier follow-up priorities

1. **Installation evidence from affected Macs.** Use the new logs to distinguish the chosen Glyphs application, its preference domain, missing configuration, a discovered default module and a failed framework load. The reported user's Mac has not been reproduced directly; a missing saved preference is a demonstrated failure mechanism, not proof of every external failure.
2. **Application discovery and Python compatibility.** Keep focused tests for renamed/duplicate Glyphs copies, distinct bundle identifiers, explicit stale preferences, official module defaults, python.org frameworks and no usable Python. Test a signed fresh install on a second real Mac before claiming wider compatibility.
3. **Export qualification.** Preserve native font compilation and private-runtime table/shaping verification. Extend the signed default-Python VM gate to variable-font exports and failure/recovery scenarios; the new build-61 gate covers six static combinations.
4. **Platform coverage.** Qualify a physical Intel Mac and exact macOS 14.0, or revise support claims with evidence. Rosetta startup is a separate result.
5. **Setup usability.** Observe installation with more than one Glyphs copy and a genuine Python failure. Check whether the scoped readiness warning, detected paths, copy selection and Install anyway wording let a user recover without support.

These are proposed directions, not new implemented features. Keep each change reviewable and test its actual behavior. Do not expand the public tool surface or package optional dependencies solely to simplify an internal implementation.

## Contributor handoff

Production code is in `src/sidecar`, `src/bridge`, `src/protocol` and `src/companions`; desktop setup is in `macos-installer`. Managed skills remain in `skills/` and are synchronized into the agent package. Optional macro iteration is preserved in `extras/`, outside the signed skill inventory. Historical qualification probes retain their original paths and versions.

Use [CODEX.md](../../CODEX.md) for build and validation instructions. Begin a new branch from main; keep release tags immutable. Preserve linked development payloads and runtime inputs when cleaning generated outputs. There is no need to reinstall or reset a user's settings for an ordinary upgrade.
