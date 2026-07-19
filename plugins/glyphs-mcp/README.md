# Glyphs MCP for Codex

This Codex plug-in connects to the Glyphs MCP server running locally at
`http://127.0.0.1:9680/mcp/` and bundles the six focused Glyphs workflows from
this repository.

Glyphs remains the editor. The embedded panel is limited to information,
review, dry runs, confirmation, progress, completion, and error feedback. It
does not expose editable paths, coordinates, metrics fields, feature code, file
navigation, arbitrary Python, tabs, or a replacement drawing canvas.

The Glyphs application and native Glyphs MCP plug-in must be installed and the
server must be running before Codex can connect.
