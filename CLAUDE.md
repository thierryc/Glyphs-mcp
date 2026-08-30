# CLAUDE.md

This guide briefs Claude Code on how to work with the Glyphs MCP repository.

## Project Overview
- Glyphs MCP ships a pinned v1.11 MCP plug-in for Glyphs 3 and an isolated,
  breaking v2 MCP plug-in for Glyphs 4.
- It exposes GlyphsApp APIs as JSON-RPC tools over the MCP Streamable HTTP transport.
- Python sources live in `src/glyphs-mcp/`; dependencies install into the user
  Scripts `site-packages` directory (not vendored into the plugin).

## Glyphs 3/v1 Capabilities Exposed to Agents
The pinned Glyphs 3/v1 tool set focuses on glyph inspection, editing, and project metadata:
- `list_open_fonts`, `get_font_masters`, `get_font_instances` for font-level information.
- `get_glyph_details`, `get_glyph_paths`, `get_glyph_components`, `get_selected_glyphs` for glyph structure.
- `create_glyph`, `delete_glyph`, `copy_glyph`, `add_component_to_glyph`, `add_anchor_to_glyph` for building glyphs.
- `update_glyph_metrics`, `update_glyph_properties`, `set_kerning_pair`, `save_font` for metrics and persistence.
- `execute_code`, `execute_code_with_context`, `get_selected_font_and_master` for scripted automation inside Glyphs.
- `docs_search`, `docs_get` for on-demand access to bundled SDK/ObjectWrapper docs.

Refer to `README.md` for the complete table of supported tools and descriptions.
Use `src/glyphs-mcp-v2/README.md` for the generic 18-tool Glyphs 4/v2 contract;
do not borrow v1 tools for v2 work.

## Glyphs 4/v2 strategy

V2 assigns facts to pinned Knowledge, judgment to managed skills, and generic
mechanics to tools. Start with `get_server_info`, then use
`list_documents`/`read_document`, observation-backed constraints, immutable
`preview_change`, and exact `apply_change`. Use detached `read_only` or
`staged_document` Python whenever the declarative surface is insufficient;
reserve `live_open_world` for live-only APIs and explicit external effects.
Python 3.14 fallback is permanent.
Registry-backed scalar entities expose their stored number through `value`;
kerning reads, numeric filters, reducers, constraints, and exact writes use
that field directly rather than requiring Python. Scalar reads include the
advertised value when projection fields are omitted.
Generate detached code only after reading
`get_server_info.data.registries.pythonExecution.detachedNamespace`; it is the
runtime source of truth for built-ins, imports, injected context, constructors,
and denials. Treat `staged_assertion_failed` as the script rejecting its own
candidate rather than evidence that detached cloning failed. An optional stale
fingerprint on `read_only` rebases to the latest stable snapshot and returns
warning evidence; staged writes still require an exact live fingerprint.

The user may save in Glyphs at any time. A save-only event does not invalidate
a preview or block document work. Active transactions retain an exactly
verified live result and reconcile history against the latest decoded saved
state. Only `save_document` enforces source/destination overwrite protection;
never confuse its file fingerprints with the live canonical document
fingerprint.

## Repository Layout Highlights
- `src/glyphs-mcp/` — MCP implementation, plugin bundle, and helper scripts.
- `src/glyphs-mcp-v2/` — Isolated, unreleased 2.0 typed runtime foundation on `lit/v2`.
- `Documentations/` — Generated ObjectWrapper docs that get copied into the plugin.
- `glyphs-build-env/` — Optional local virtual environment for development tooling.
- `README.md` — High-level overview, tool catalog, and IDE configuration snippets.

## Glyphs 3/v1 Build & Run Workflow
1. Install dependencies using one option:
   - `src/glyphs-mcp/scripts/install_deps_glyphs_python.sh` (uses Glyphs’ Python → installs into `~/Library/Application Support/Glyphs 3/Scripts/site-packages`), or
   - `src/glyphs-mcp/scripts/install_deps_external_python.sh` (uses external Python → installs into that Python’s user site-packages)
2. Copy or symlink `src/glyphs-mcp/Glyphs MCP.glyphsPlugin` into `~/Library/Application Support/Glyphs 3/Plugins/`.
3. Restart Glyphs, then choose **Edit → Start MCP Server**. The server listens on `http://127.0.0.1:9680/mcp/` using Streamable HTTP.

After regenerating ObjectWrapper documentation, update the bundled copy with:

```
python src/glyphs-mcp/scripts/copy_documentation.py
```

The v2 source remains isolated from the pinned 1.x source. Run its tests
through the repository suite and assemble its two deterministic target
layouts without modifying v1:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHON_BIN=.venv-v2/bin/python ./scripts/run_python_tests.sh
.venv-v2/bin/python scripts/build_v2_runtime_payload.py
```

Keep v2 environments and generated state inside `.venv-v2/`, `.cache/v2/`,
`build/`, and `dist/` in this worktree.

## Security & Transport Notes
- The server binds locally starting at port 9680; keep it on loopback during development.
- Responses stream via MCP Streamable HTTP (SSE under the hood); preserve any `Mcp-Session-Id` header returned by the server.
- If you open `http://127.0.0.1:9680/mcp/` in a browser, the server returns a JSON discovery payload; MCP clients should connect with `Accept: text/event-stream`.
- Add authentication (for example bearer tokens) before exposing the transport beyond localhost.

## Helper Resources
- Guide: `glyphs://glyphs-mcp/guide`
- Docs index: `glyphs://glyphs-mcp/docs/index.json`

## Agent Execution Contract (Guide-Aligned)

The commands below describe Glyphs 3/v1. V2 agents must follow the generic
strategy above and the v2 runtime contract.
- Read context before any mutation (`get_selected_font_and_master`, `get_selected_glyphs`, plus glyph detail/path reads as required).
- Prefer dedicated tools first; use `execute_code_with_context` or `execute_code` early for complex multi-step workflows when one scripted pass is more reliable.
- In `execute_code*`, validate targets before edits, keep scripts focused, and cap output with `max_output_chars` / `max_error_chars` when needed.
- Verify by reading back and report changed/skipped counts and unresolved risks.

## Client Configuration
Use direct HTTP clients for local setup. The recommended commands are:

```bash
codex mcp add glyphs-mcp-server --url http://127.0.0.1:9680/mcp/
```

```bash
claude mcp add --scope user --transport http glyphs-mcp http://127.0.0.1:9680/mcp/
```

Then start the server in Glyphs with **Edit → Start MCP Server**.
