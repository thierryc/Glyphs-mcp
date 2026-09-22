# Glyphs MCP agent plugin

This optional repository plugin connects Codex/ChatGPT, Claude Code, Cursor,
and GitHub Copilot CLI to the Glyphs MCP server at
`http://127.0.0.1:9680/mcp/`. Version 2.0.0 bundles the general Glyphs launcher
and 10 managed skills, including the general launcher, reviewed workspace scripting,
and reusable development, for every host.

Host-native manifests live under `.codex-plugin/`, `.claude-plugin/`,
`.cursor-plugin/`, and `.github/plugin/`. They all reference this package's
single `skills/` directory and `.mcp.json`. Skills inherit the package version;
the project version is 2.0.0, with bridge and sidecar components at 0.1.0.
Glyphs 3 uses the separate pinned 1.11.0 bundle and skills.

Glyphs remains the editor. The native bridge panel displays its status and a
heart button for Welcome & Support. The AI client receives reports and structured
results from twelve tools. `accept_job` verifies targets and persists the whole
document; Undo and Redo are grouped per glyph, and discard restores an
unaccepted job with conflict checks.

Glyphs-native commands use the capability-gated `native_action` job family, not
additional tools. The running bridge publishes its filtered closed action
catalog; requests never contain Python, menu names or arbitrary selectors.

The Glyphs application and native Glyphs MCP plug-in must be installed and the
server must be running before the host can connect. Installing this agent
plugin is not required: standalone skills and manual MCP configuration remain
supported. Every supported client receives concise text and structured tool results.

See the repository documentation for the
[plugin UI](../../content/getting-started/codex-chatgpt-plugin-ui.mdx) and
[cross-client skill setup](../../content/getting-started/use-agent-skills.mdx).

The lean Glyphs 4 package exposes twelve tools: get_status, list_documents,
read_entities, start_job, get_job, apply_job, accept_job, discard_job,
save_document, start_edit_workflow, get_edit_workflow and respond_edit_workflow. There is no arbitrary Python execution tool. Install the pinned
Glyphs 3 skills separately when using the 1.11.0 server.

## Conversation interface

Use one standard MCP App in compatible hosts, including the existing local
Claude Desktop transport and Cursor's documented MCP Apps support. Detect
Codex's actual host capabilities; do not infer them from ChatGPT. CLI clients
and failed/missing UI bridges retain the full text workflow. The shared skills
and server descriptions map natural-language choices to retained actions.

Save and continue saves existing work once and resumes the request. Complete
results apply automatically; previews, warnings and required overwrites wait
for review. The resulting edit is not saved without separate authorization.
