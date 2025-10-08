# Glyphs MCP
![Glyphs MCP splash](/images/glyphs-app-mcp/glyphs-mcp.webp)

A Machine-Control-Protocol server for [Glyphs](https://glyphsapp.com) that exposes font-specific tools to AI and LLM agents.

---

## What is an MCP server?
A *Model Context Protocol* server is a lightweight process that:

1. **Registers tools** (JSON-RPC methods) written in the host language (Python here).
2. **Streams JSON output** back to the calling agent.

Bridging Glyphs with MCP makes it possible for assistants to read, inspect, and manipulate Glyphs documents in the same way a human operator would.

---

## Table of contents
- [Command set (v0.3)](#command-set-v0-3)
- [Client setup](#client-setup)
  - [OpenAI Codex CLI](#openai-codex-cli)
  - [Claude Desktop](#claude-desktop)
  - [Cursor IDE](#cursor-ide)
  - [Windsurf](#windsurf)
  - [Claude Code (VS Code)](#claude-code-vs-code)
  - [Continue (VS Code / JetBrains)](#continue-vs-code-jetbrains)
- [Access & contributing](#access-contributing)
- [Build the Glyphs plug-in](#build-the-glyphs-plug-in)

---

## Command set (v0.3)
| Tool | Description |
|------|-------------|
| `list_open_fonts` | List all open fonts and basic metadata. |
| `get_font_glyphs` | Return glyph list and key attributes for a font. |
| `get_font_masters` | Detailed master information for a font. |
| `get_font_instances` | List instances and their interpolation data. |
| `get_glyph_details` | Full glyph data including layers, paths, components. |
| `get_font_kerning` | All kerning pairs for a given master. |
| `create_glyph` | Add a new glyph to the font. |
| `delete_glyph` | Remove a glyph from the font. |
| `update_glyph_properties` | Change unicode, category, export flags, etc. |
| `copy_glyph` | Duplicate outlines or components from one glyph to another. |
| `update_glyph_metrics` | Adjust width and side-bearings. |
| `get_glyph_components` | Inspect components used in a glyph. |
| `add_component_to_glyph` | Append a component to a glyph layer. |
| `add_anchor_to_glyph` | Add an anchor to a glyph layer. |
| `set_kerning_pair` | Set or remove a kerning value. |
| `get_selected_glyphs` | Info about glyphs currently selected in UI. |
| `get_selected_font_and_master` | Current font + master and selection snapshot. |
| `get_glyph_paths` | Export paths in a JSON format suitable for LLM editing. |
| `set_glyph_paths` | Replace glyph paths from JSON. |
| `execute_code` | Execute arbitrary Python in the Glyphs context. |
| `execute_code_with_context` | Execute Python with injected helper objects. |
| `save_font` | Save the active font (optionally to a new path). |

---

## Client setup
Configure your preferred AI client to speak the Streamable HTTP endpoint. Below are quick-start snippets for common tools.

### OpenAI Codex CLI
![OpenAI Codex MCP configuration screenshot](/images/glyphs-app-mcp/codex-in-vs-code.webp)
![OpenAI Codex result screenshot](/images/glyphs-app-mcp/codex-result-in-vs-code.webp)

Codex understands MCP servers via `codex mcp` helpers. The `mcp-remote` transport is the preferred option, but it requires Node 20 or newer on your system. Add the configuration to `~/.codex/config.toml`, then restart any active Codex sessions.

```toml
[mcp_servers.glyphs-app-mcp]
command = "npx"
args = ["mcp-remote", "http://127.0.0.1:9680/mcp/", "--header"]
```

You can run `codex config path` to verify the location if you've customised the CLI setup.

### Claude Desktop
![Claude Desktop MCP registry screenshot](/images/glyphs-app-mcp/claude-sonnet.webp)

Claude Desktop reads configuration from `/Users/<userName>/Library/Application Support/Claude/claude_desktop_config.json`. Append the server definition and restart the app:

```json
{
  "globalShortcut": "Alt+Ctrl+Cmd+*",
  "mcpServers": {
    "glyphs-mcp-server": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://127.0.0.1:9680/mcp/"
      ],
      "env": {
        "PATH": "/Users/yourUserName/.nvm/versions/node/v22.19.0/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
      }
    }
  }
}
```

Claude Desktop spawns MCP servers without your interactive shell profile, and its bundled Node runtime is typically older than v20. Because `mcp-remote` itself targets Node 20+, the explicit `PATH` entry forces `npx` to resolve to your local Node 22 installation so the CLI boots successfully.

Prefer Python tooling instead of Node? Install the proxy from PyPI and point Claude directly at the Python binary:

```bash
pip3 install --user mcp-proxy
# upgrade later with: python3.12 -m pip install --user --upgrade mcp-proxy
```

```json
{
  "globalShortcut": "Alt+Ctrl+Cmd+*",
  "mcpServers": {
    "glyphs-mcp-server": {
      "command": "/Library/Frameworks/Python.framework/Versions/3.12/bin/mcp-proxy",
      "args": [
        "--transport",
        "streamablehttp",
        "http://127.0.0.1:9680/mcp/"
      ],
      "env": {
        "PATH": "/Library/Frameworks/Python.framework/Versions/3.12/bin:/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
      }
    }
  }
}
```

Claude Desktop still discards your login shell. The explicit `PATH` entry ensures the app finds the `mcp-proxy` shim that `pip3` drops into Python 3.12’s `bin` directory before falling back to the system defaults. If your Python lives elsewhere (for example a `pyenv` or Homebrew install), replace `/Library/Frameworks/Python.framework/Versions/3.12/bin` with the result of `python3 -m site --user-base` plus `/bin`.

Prefer invoking the all-in-one helper? Swap in `@modelcontextprotocol/server-everything` or the dedicated SSE client:

```json
{
  "globalShortcut": "Alt+Ctrl+Cmd+*",
  "mcpServers": {
    "glyphs-mcp-server": {
      "command": "npx",
      "args": [
        "-y",
        "@modelcontextprotocol/server-everything"
      ],
      "env": {
        "SSE_URL": "http://127.0.0.1:9680/mcp/"
      }
    }
  }
}
```

### Cursor IDE
![Cursor MCP configuration screenshot](/images/glyphs-app-mcp/cursor-gemini.webp)

Cursor stores its MCP registry in `~/.cursor/mcp.json`. Drop in the JSON below to wire up the Glyphs server—the `PATH` override makes sure `npx` resolves to your Node 20+ install so `mcp-remote` can launch:

```json
{
  "mcpServers": {
    "glyphs-mcp-server": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://127.0.0.1:9680/mcp/"
      ],
      "env": {
        "PATH": "/Users/yourUserName/.nvm/versions/node/v22.19.0/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"
      }
    }
  }
}
```

Cursor still honours the legacy YAML file if you prefer that format:

```yaml
mcpServers:
  - name: glyphs-mcp
    type: streamable-http
    url: http://127.0.0.1:9680/mcp/
```

### Windsurf
![Windsurf MCP integration screenshot](/images/glyphs-app-mcp/windsurf.webp)
![Windsurf MCP configuration screenshot](/images/glyphs-app-mcp/windsurf-config.webp)

Windsurf reads MCP configuration from `~/.codeium/windsurf/mcp_config.json`. Use the streamlined serverUrl format:

```json
{
  "mcpServers": {
    "glyphs-mcp-server": {
      "serverUrl": "http://127.0.0.1:9680/mcp/"
    }
  }
}
```

### Claude Code (VS Code)
Use the Claude CLI to register the MCP server directly. The VS Code extension will discover it automatically:

```bash
claude mcp add --transport http glyphs-mcp-server http://127.0.0.1:9680/mcp/
```

After adding, reload VS Code (or the Claude extension) if it’s already running.

### Continue (VS Code / JetBrains)
![Continue MCP configuration screenshot](/images/glyphs-app-mcp/continue-in-vs-code.webp)

Continue supports MCP through YAML configuration. Drop the snippet below into `~/.continue/config.yaml` (or a workspace override):

```yaml
mcpServers:
  - name: Glyphs MCP
    # Local MCP server using Streamable HTTP transport
    type: streamable-http
    url: http://127.0.0.1:9680/mcp/
```

To scope the server to a single project, create a workspace override at `./.continue/config.yaml` in your repository:

```yaml
name: New MCP server
version: 0.0.1
schema: v1
mcpServers:
  - name: Glyphs MCP
    # Local MCP server using Streamable HTTP transport
    type: streamable-http
    url: http://127.0.0.1:9680/mcp/
```

If you start Continue before launching Glyphs, open the MCP submenu inside the Continue sidebar and click **Reload** so the editor picks up the freshly started server.

#### VS Code discovery shortcut
If you prefer to let VS Code auto-discover MCP servers registered by Claude Desktop, Cursor, or other tools, flip on the built-in discovery toggle via `vscode://settings/chat.mcp.discovery.enabled`. Once the setting is enabled, restart the chat session and the `glyphs-mcp-server` entry should appear without manual YAML edits.

---

## Access & contributing
PRs, test reports, and ideas are always welcome. The semi-private repository lives at [github.com/thierryc/Glyphs-mcp](https://github.com/thierryc/Glyphs-mcp). Send a direct message on the Glyphs Forum to unlock access: [Exploring the role of AI in typeface design](https://forum.glyphsapp.com/t/exploring-the-role-of-ai-in-typeface-design-with-glyphs/33343/63).

Questions? Say hello at [thierry@anotherplanet.io](mailto:thierry@anotherplanet.io) or [@anotherplanet_io](https://www.instagram.com/anotherplanet_io/). When you are done, head back [home](/) for the full portfolio.

---

## Build the Glyphs plug-in
```bash
# from the project root
source glyphs-build-env/bin/activate

# pull vendored libs & build the bundle
src/glyphs-mcp/scripts/vendor_deps.sh
```

The script updates the plug-in `site-packages` located in `src/glyphs-mcp/Glyphs MCP.glyphsPlugin`. Copy or symlink that bundle into `~/Library/Application Support/Glyphs 3/Plugins/`, then restart Glyphs.

If you regenerate the ObjectWrapper documentation, refresh the bundled copy with:

```bash
python src/glyphs-mcp/scripts/copy_documentation.py
```

Once installed, open Glyphs and choose **Edit → Start MCP Server**. The service listens on `http://127.0.0.1:9680/` using the MCP Streamable HTTP transport. Open the **Macro Panel** to monitor console output.
