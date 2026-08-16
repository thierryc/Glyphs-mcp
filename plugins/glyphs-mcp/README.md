# Glyphs MCP agent plugin

This optional repository plugin connects Codex/ChatGPT, Claude Code, Cursor,
and GitHub Copilot CLI to the Glyphs MCP server at
`http://127.0.0.1:9680/mcp/`. Version 1.11.0 bundles the same general Glyphs
launcher and 10 focused workflows, including safe live scripting and reusable
development, for every host.

Host-native manifests live under `.codex-plugin/`, `.claude-plugin/`,
`.cursor-plugin/`, and `.github/plugin/`. They all reference this package's
single `skills/` directory and `.mcp.json`. Skills inherit the package version;
the MCP server reports the aligned native Glyphs MCP version.

Glyphs remains the editor. The embedded panel is limited to information,
review, dry runs, confirmation, progress, completion, and error feedback. It
does not expose editable paths, coordinates, metrics fields, feature code, file
navigation, arbitrary Python, tabs, or a replacement drawing canvas.

The Glyphs application and native Glyphs MCP plug-in must be installed and the
server must be running before the host can connect. Installing this agent
plugin is not required: standalone skills and manual MCP configuration remain
supported. Clients that do not support the embedded MCP App still receive
concise text and structured tool results.

See the repository documentation for the
[plugin UI](../../content/getting-started/codex-chatgpt-plugin-ui.mdx) and
[cross-client skill setup](../../content/getting-started/use-agent-skills.mdx).
