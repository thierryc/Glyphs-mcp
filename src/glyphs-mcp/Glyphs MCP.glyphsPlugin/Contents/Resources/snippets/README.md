Snippets for Glyphs MCP

This folder contains small, focused Python snippets designed to run in the Glyphs environment via MCP tools. Each snippet is a JSON file with the following schema:

- `id` (string): Unique identifier (kebab-case).
- `title` (string): Short human-friendly title.
- `description` (string): What the snippet does and when to use it.
- `tags` (array of strings): Labels for filtering (e.g. `components`, `anchors`, `metrics`).
- `code` (string): Python code intended for the Glyphs API context.
- `license` (string): SPDX-style license tag (e.g. `MIT`, `Apache-2.0`, `BSD-3-Clause`).
- `source` (string, optional): URL to upstream source or documentation.

Usage
- Use the MCP tools `list_snippets` and `get_snippet` to browse and retrieve snippets.
- The `code` field is suitable for `execute_code` or `execute_code_with_context` tools.

Notes
- Include only open-source material (MIT/Apache/BSD or similar). Credit sources via the `source` field and provide the license.
- Keep snippets short and task-oriented. Prefer patterns that are broadly useful for agent workflows.

