# Glyphs MCP for ChatGPT and Codex

This repository plugin connects ChatGPT and Codex to the Glyphs MCP server at
`http://127.0.0.1:9680/mcp/` and bundles a general Glyphs launcher plus seven
focused workflows from this repository.

Glyphs remains the editor. The embedded panel is limited to information,
review, dry runs, confirmation, progress, completion, and error feedback. It
does not expose editable paths, coordinates, metrics fields, feature code, file
navigation, arbitrary Python, tabs, or a replacement drawing canvas.

The Glyphs application and native Glyphs MCP plug-in must be installed and the
server must be running before the host can connect. Clients that do not support
the embedded MCP App still receive concise text and structured tool results.

See the repository documentation for the
[plugin UI](../../content/getting-started/codex-chatgpt-plugin-ui.mdx) and
[cross-client skill setup](../../content/getting-started/use-agent-skills.mdx).
