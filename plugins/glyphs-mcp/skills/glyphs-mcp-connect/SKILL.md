---
name: glyphs-mcp-connect
description: Use this skill when the task is to connect an MCP client to the local Glyphs MCP server, verify the endpoint, choose the right tool profile, or run a first health check with `get_server_info` and `list_open_fonts`.
---

# Glyphs MCP connect

Use this skill for local Glyphs MCP startup and connection checks.

## Core rules

- Use the client MCP server settings' Direct connection mode with the local Streamable HTTP endpoint: `http://127.0.0.1:9680/mcp/`
- Prefer a narrower tool profile before connecting so the client sees fewer tools and schemas.
- If connection fails, restart Glyphs, start the MCP server, then reload or relaunch the client.
- Treat `get_server_info` as the first health check, then call `list_open_fonts`.
- Do not use `curl` for normal verification; use it only as a fallback to isolate endpoint reachability when MCP tools are unavailable.

## Workflow

1. Tell the user to start Glyphs and confirm the server is running from **Edit -> Glyphs MCP Server Status...**.
2. Recommend the narrowest useful profile first:
   - `Core (Read-only)` for inspection
   - `Kerning`, `Spacing`, `Kerning + Spacing`, `Paths / Outlines`, or `Editing` for focused tasks
3. Add the server in the MCP client's server settings using Direct connection mode and URL `http://127.0.0.1:9680/mcp/`.

4. After adding or changing the MCP server, suggest starting a new conversation so the client loads the Glyphs MCP tool list properly.
5. Verify the connection by calling `get_server_info`, then `list_open_fonts`.
6. Report:
   - `version`, `runtimeId`, and `resourcesPath`
   - how many fonts are open
   - `familyName` and `filePath` for each
   - which `font_index` to use next
7. If the call fails, quote the error verbatim and fall back to startup-order troubleshooting.

## Deeper references

- [Connect a client](https://github.com/thierryc/Glyphs-mcp/blob/main/content/getting-started/connect-client.mdx)
- [First session](https://github.com/thierryc/Glyphs-mcp/blob/main/content/tutorial/first-session.mdx)
- [Project briefing](https://github.com/thierryc/Glyphs-mcp/blob/main/CODEX.md)
