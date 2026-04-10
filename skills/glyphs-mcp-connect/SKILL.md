---
name: glyphs-mcp-connect
description: Use this skill when the task is to connect Codex to the local Glyphs MCP server, verify the endpoint, choose the right tool profile, or run a first health check with `list_open_fonts`.
---

# Glyphs MCP connect

Use this skill for local Glyphs MCP startup and connection checks.

## Core rules

- Use the local Streamable HTTP endpoint: `http://127.0.0.1:9680/mcp/`
- Prefer a narrower tool profile before connecting so Codex sees fewer tools and schemas.
- If connection fails, restart Glyphs, start the MCP server, then reload or relaunch Codex.
- Treat `list_open_fonts` as the first health check.

## Workflow

1. Tell the user to start Glyphs and confirm the server is running from **Edit -> Glyphs MCP Server Status...**.
2. Recommend the narrowest useful profile first:
   - `Core (Read-only)` for inspection
   - `Kerning`, `Spacing`, `Kerning + Spacing`, `Paths / Outlines`, or `Editing` for focused tasks
3. Add the server in Codex:

```bash
codex mcp add glyphs-mcp-server --url http://127.0.0.1:9680/mcp/
codex mcp list
```

4. Verify the connection by calling `list_open_fonts`.
5. Report:
   - how many fonts are open
   - `familyName` and `filePath` for each
   - which `font_index` to use next
6. If the call fails, quote the error verbatim and fall back to startup-order troubleshooting.

## Deeper references

- [Connect a client](../../content/getting-started/connect-client.mdx)
- [First session](../../content/tutorial/first-session.mdx)
- [Project briefing](../../CODEX.md)
