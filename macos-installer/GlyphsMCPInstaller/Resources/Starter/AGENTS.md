# {{PROJECT_NAME}}

Use $glyphs-mcp-development for a Glyphs 4 coding session: create or revise
workspace scripts/plugins using its installed offline SDK/API corpus and helper.
Offline creation and validation need no connection, open font or Save.
For OpenType source work use $glyphs-mcp-opentype-features and its native workflow.
For live font-design work use $glyphs on the {{SERVER_NAME}} MCP connection at
{{ENDPOINT_URL}}. Verify its catalog and get_status. Discover the intended font
once with list_documents; retain its connection-specific document_id for fresh
read_entities calls. Rediscover after document_not_found, target change or a
bridge/Glyphs restart, not a missing glyph. Never substitute another open font.
Prepare supported edits with start_job, review get_job, then apply_job. Native
Save accepts changes; existing Undo/Redo and discard_job remain available.
Reconcile uncertain writes with the existing job ID. There is no arbitrary MCP
Python or plugin reload tool. Native installation, execution and restart follow
the user's authorised task; use disposable fonts and preserve unrelated work.
Glyphs 3 uses its separate pinned 1.11.0 contract and skills.
