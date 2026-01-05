# Glyphs MCP Guide

Glyphs MCP is a local MCP server that runs inside Glyphs 3.

Primary goal: **execute tools safely and correctly** (including `execute_code*`) to inspect and edit fonts/glyphs in the running app.

Resources are **helpers**: they provide reference material (e.g., API documentation) so the assistant can write better GlyphsApp/Python code with fewer mistakes.

## Connection

- Endpoint: `http://127.0.0.1:9680/mcp/`
- Transport: MCP Streamable HTTP (SSE)
- Clients should connect with `Accept: text/event-stream`
- The server may return an `Mcp-Session-Id` header; clients should reuse it.

## Security

This server is designed for localhost use.

- Origin allowlist: set `GLYPHS_MCP_ALLOWED_ORIGINS` (comma-separated hostnames) to restrict requests with an `Origin` header.
- Optional auth token: set `GLYPHS_MCP_AUTH_TOKEN` and send it as:
  - `Authorization: Bearer <token>`, or
  - `Mcp-Auth-Token: <token>`

### About `execute_code`

`execute_code` and `execute_code_with_context` can run arbitrary Python in the Glyphs process.

Recommended usage pattern:
1. Prefer dedicated tools (glyph inspection/editing) first.
2. Use `execute_code*` only when needed, and keep scripts minimal.
3. Print clear results and avoid destructive operations unless explicitly requested.

## Docs and Resources

If you need Glyphs SDK / ObjectWrapper reference:
- Use the documentation index resource and fetch specific pages as needed.

