# {{PROJECT_NAME}} — Project directives (Glyphs MCP)

This project assumes the **Glyphs MCP** plug-in is installed and the server is running in Glyphs.

## MCP server
- Server name: `{{SERVER_NAME}}`
- Endpoint: `{{ENDPOINT_URL}}`

## Rules for agents
- Use the `{{SERVER_NAME}}` MCP tools for all Glyphs/font operations; do not guess state.
- Run a connectivity check with `tools/list`, then call `get_server_info` and
  follow the reported API major. If discovery fails, retry once with a new
  Streamable HTTP session and `Mcp-Session-Id`.
- On Glyphs 4/v2, use Knowledge for facts, skills for typographic judgment,
  and generic tools for mechanics: `list_documents`, `read_document`,
  constraints, immutable `preview_change`, exact `apply_change`, verification,
  and `revert_change`. Use permanent Python fallback when generic mechanics
  are insufficient.
- Before generating detached v2 Python, inspect
  `get_server_info.data.registries.pythonExecution.detachedNamespace` for the
  effective Python 3.14 namespace and its contract fingerprint.
- A user may save in Glyphs at any time. A save-only event never stales a v2
  preview or blocks unrelated work. Keep live-document fingerprints separate
  from source/destination file fingerprints; file overwrite protection belongs
  only to `save_document`.
- On pinned Glyphs 3/v1, use its discovered read/review/dry-run/confirmation
  contract. Never mix v1 and v2 tool names.
- If connection fails, instruct the user to open Glyphs and run **Edit → Glyphs MCP Server**, then retry.
- Route with the catalog titles, descriptions, and safety annotations; use focused Glyphs MCP skills for multi-step workflows.
