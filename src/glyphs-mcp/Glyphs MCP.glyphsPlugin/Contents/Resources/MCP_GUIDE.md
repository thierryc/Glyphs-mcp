# Glyphs MCP Guide

Glyphs MCP is a local MCP server that runs inside Glyphs 3.

Primary goal: **execute tools safely and correctly** (including `execute_code*`) to inspect and edit fonts/glyphs in the running app.

Resources are **helpers**: they provide reference material (e.g., API documentation) so the assistant can write better GlyphsApp/Python code with fewer mistakes.

## Connection

- Endpoint: `http://127.0.0.1:9680/mcp/`
- Transport: MCP Streamable HTTP (SSE)
- Clients should connect with `Accept: text/event-stream`
- The server may return an `Mcp-Session-Id` header; clients should reuse it.
- If your coding agent doesn't connect, launch Glyphs fresh and start the MCP server first, then launch the coding agent afterwards.

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

Performance tips (especially for batch operations across many masters):
- Prefer a single `execute_code*` call over many small ones.
- Avoid chatty `print()` in tight loops. Use one summary line per large unit of work.
- Use `capture_output=false` to avoid buffering stdout/stderr into the MCP response.
- Use `max_output_chars` / `max_error_chars` to cap returned output and keep responses small.
- Avoid calling `exit()` / `quit()` / `sys.exit()` in `execute_code*`.

## Docs and Resources

If you need Glyphs SDK / ObjectWrapper reference:
- Use `docs_search` to find relevant pages, then `docs_get` to fetch them on demand.
- The docs index is also available as a resource: `glyphs://glyphs-mcp/docs/index.json`

By default, individual doc pages are not registered as separate resources (to avoid flooding MCP clients). If you really want per-page resources, call `docs_enable_page_resources` (or set `GLYPHS_MCP_REGISTER_DOC_PAGES=1`).
