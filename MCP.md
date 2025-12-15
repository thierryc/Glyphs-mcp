Personnal note Wrok in progress 

Claude desktop Install

code ~/Library/Application\ Support/Claude/claude_desktop_config.json

Note: `/mcp/` is an SSE MCP endpoint. Browsers will show a small JSON discovery response; MCP clients connect with `Accept: text/event-stream`.

```

{
  "globalShortcut": "Alt+Ctrl+Cmd+*",
  "mcpServers": {
    "glyphs-mcp-server": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "http://127.0.0.1:9680/mcp/"
      ]
    }
  }
}



```

```

{
  "globalShortcut": "Alt+Ctrl+Cmd+*",
  "mcpServers": {
    "glyphs-mcp-server": {
      "command": "mcp-proxy",
      "args": [
        "--transport",
        "streamablehttp",
        "http://127.0.0.1:9680/mcp/"
      ]
    }
  }
}


```
