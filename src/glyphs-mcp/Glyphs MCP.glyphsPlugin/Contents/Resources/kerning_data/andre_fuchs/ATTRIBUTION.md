# Andre Fuchs kerning-pairs (MIT) — bundled snapshot

Source repository: https://github.com/andre-fuchs/kerning-pairs

This plug-in ships a **normalized JSON snapshot** of Andre Fuchs’ relevance-ranked kerning pairs so the MCP server can work **offline**.

## Notes

- The file `relevant_pairs.v1.json` is a normalized format (left/right as single Unicode characters).
- The snapshot included in this repo may be a **small seed subset** depending on how it was generated.
  - To regenerate/update it from an upstream export, use:
    - `python3 /Users/thierryc/Dev/github/thierryc/Glyphs-mcp/src/glyphs-mcp/scripts/vendor_andre_fuchs_pairs.py <path-to-upstream-json-or-txt>`
- When regenerating, update the embedded `commit` field if you know the upstream commit hash.

