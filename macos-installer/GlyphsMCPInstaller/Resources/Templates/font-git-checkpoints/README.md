# {{PROJECT_NAME}}

Place your own .glyphs or .glyphspackage font in sources. This template contains no font.
The app explicitly initializes a new Git repository when creating this project.
Set your Git name and email before the first checkpoint.

The project setting in .glyphs-mcp.json enables local font checkpoints. Before an authorized
edit, MCP records the saved baseline without saving again. After an authorized MCP Save,
MCP commits only that font and its action record. Keep without saving creates no result
checkpoint. Save and Git are separate outcomes; retrying a failed checkpoint never saves again.
No push or unrelated staged changes are included. Repositories with active commit hooks,
byte-transforming attributes, conflicts or staged changes to the intended font need manual resolution.

Ask in chat to show recent checkpoints, actions, compare two versions or restore one.
The app exposes the same history for fonts open in Glyphs. Restore replaces all later changes
in that font, including unsaved edits, and clears Undo history. It loads in Glyphs without
rewriting the current file; save the restored result only when authorized. Git history stays intact.

Action records live in .glyphs-mcp/actions/<font-path-hash>/<save-id>.json.
See documentation/action-record-schema.json. Scope references resolve within the same Git commit.
Records distinguish execution, verification and possible manual edits; they contain no chat transcript.
