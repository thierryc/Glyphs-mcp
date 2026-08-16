---
name: glyphs
description: Use this skill as the general Glyphs MCP entry point for inspecting or editing an open Glyphs font, checking the local server and font context, or choosing the safest focused Glyphs MCP workflow for a font task.
---

# Glyphs MCP

Use this skill as the general launcher for Glyphs MCP tasks.

## Core rules

- Read the current server, font, master, glyph, layer, and selection context needed for the request before acting.
- Prefer the narrowest dedicated MCP tool and focused workflow that fits the task.
- Before mutation, review or dry-run when supported, explain the exact proposed change, and require explicit approval for confirm-gated actions.
- Re-read affected state after mutation and report changed, skipped, and unresolved items.
- Never auto-save the font.

## Route focused work

- OpenType features and stylistic sets: follow `glyphs-mcp-features`.
- Live Python runs, Macro Panel snippets, and iterative script debugging: follow `glyphs-mcp-scripting`.
- Reusable Python scripts and plug-in development: follow `glyphs-mcp-development`.
- Icon-font Unicode or PUA assignments: follow `glyphs-mcp-icon-font`.
- Kerning collision review and bumper changes: follow `glyphs-mcp-kerning`.
- LitSquare metadata, inherited settings, or semantic path roles: follow `glyphs-mcp-litsquare-metadata`.
- Spacing, sidebearings, and width review: follow `glyphs-mcp-spacing`.
- Outlines, components, anchors, selected nodes, or bundled docs: follow `glyphs-mcp-outlines-docs`.
- Roman-to-italic or oblique first passes: follow `glyphs-mcp-italic-first-pass`.
- Generic Python with no Glyphs app or font target does not use a Glyphs skill.
- For other tasks, use the smallest relevant Glyphs MCP tool set and keep the same review-first safety rules.

## Connection and context workflow

1. If connection or font context is unknown, call `get_server_info`, then `list_open_fonts`.
2. If no server is available, ask the user to start Glyphs and confirm the server is running from **Edit -> Glyphs MCP Server Status...**. Use the local endpoint `http://127.0.0.1:9680/mcp/`.
3. Resolve the target font and current master or selection before continuing.
4. Follow the matching focused workflow, or complete an unmatched task with dedicated tools.
5. Summarize the result and any manual review still needed.

## Deeper references

- [First session](https://github.com/thierryc/Glyphs-mcp/blob/main/content/tutorial/first-session.mdx)
- [Command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)
- [Project briefing](https://github.com/thierryc/Glyphs-mcp/blob/main/CODEX.md)
