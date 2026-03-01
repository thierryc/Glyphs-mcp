# {{PROJECT_NAME}} — Project directives (Glyphs MCP)

This project assumes the **Glyphs MCP** plug-in is installed and the server is running in Glyphs.

## MCP server
- Server name: `{{SERVER_NAME}}`
- Endpoint: `{{ENDPOINT_URL}}`

## Rules for agents
- Use the `{{SERVER_NAME}}` MCP tools for all Glyphs/font operations; do not guess state.
- Run a connectivity check by calling `tools/list` (or `list_open_fonts`). If it fails, retry once after forcing a new Streamable HTTP session (new SSE connection / new `Mcp-Session-Id`). If you can’t re-handshake in this client, tell me explicitly and I’ll start a new chat.
- If a task might change a font, first call `list_open_fonts` and any relevant read-only tools to collect context.
- Prefer tools that support `dry_run` first; only mutate when explicitly requested and when the tool requires `confirm=true`.
- If connection fails, instruct the user to open Glyphs and run **Edit → Start MCP Server**, then retry.
- If tokens/tool lists are large, select a narrower Tool Profile in **Edit → Glyphs MCP Server Status…** before reconnecting the client.
