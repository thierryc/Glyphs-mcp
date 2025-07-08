Personnal note Wrok in progress 

Claude desktop Install

code ~/Library/Application\ Support/Claude/claude_desktop_config.json


```

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
        "SSE_URL": "http://127.0.0.1:9680/sse/"
      }
    }
  }
}



```

```

{
  "globalShortcut": "Alt+Ctrl+Cmd+*",
  "mcpServers": {
    "glyphs-mcp-server": {
      "command": "sse-mcp-client",
      "args": [
        "--url",
        "http://127.0.0.1:9680/sse/"
      ]
    }
  }
}


```