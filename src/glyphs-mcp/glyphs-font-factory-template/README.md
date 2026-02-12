# Glyphs Font Factory (Template)

Creates a new Glyphs variable font from scratch using the Glyphs MCP server.

## Requirements

- Glyphs.app running
- Glyphs MCP server/plugin available

## Workflow

1. Open this folder in Codex.
2. Ask: `create a new variable font`
3. Follow the interview in `AGENTS.md`.
4. The agent generates a new `.glyphs` source in `sources/` by running GlyphsApp code via MCP.
5. Draw root glyphs (the scaffold is structural; outlines start empty).
6. Run the rebuild script from `AGENTS.md` to update anchors and regenerate composites.
7. Export fonts to `exports/` (manual export step in Glyphs).

## Rules

- Do not edit `.glyphs` files directly (no patching/parsing). All source writes happen via Glyphs.app save.

