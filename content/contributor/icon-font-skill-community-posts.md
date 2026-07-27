---
title: Icon-font skill community post drafts
description: Draft announcements for the Glyphs Forum and LinkedIn.
---

# Icon-font skill community post drafts

## Glyphs Forum

### Suggested title

Glyphs MCP: a review-first workflow for Unicode and PUA assignments

### Post

Following up on the discussion in [PUA encoding best practices](https://forum.glyphsapp.com/t/pua-encoding-best-practices/13912), I added a small icon-font encoding skill to [Glyphs MCP](https://github.com/thierryc/Glyphs-mcp).

The recurring problem is not how to count upward from `E000`. It is how to avoid collisions, preserve assignments after a font has shipped, and keep a clear boundary between real characters, private characters, and glyph variants.

The MCP implementation is deliberately generic:

- `review_unicode_assignments` audits the font and can propose deterministic assignments;
- `apply_unicode_assignments` applies only an explicit reviewed batch;
- the complete font participates in collision checks, even when the target is a selection;
- existing and multiple Unicode assignments are preserved;
- removed entries from a supplied previous map stay reserved;
- automatic allocation skips occupied values, caller reservations, surrogates, and noncharacters;
- apply supports a dry run, checks the expected before-state, verifies the result, rolls back a failed batch, and never saves the font.

The new `glyphs-mcp-icon-font` skill is the icon-specific operating layer. It tells the agent to audit first, use selected or named glyphs by default, and require the previous mapping before allocating new values in a released font. If that mapping is missing, the skill can still report the current state, but it stops before allocation unless the user explicitly decides to establish a new baseline.

It does not infer a Unicode character from an icon name or drawing. It does not create CSS, TypeScript, manifests, Figma assets, or accessibility metadata. Drawing and spacing remain separate workflows.

The default allocation range is the BMP Private Use Area, but it is only a default:

- BMP PUA: `U+E000–U+F8FF`
- Supplementary PUA-A: `U+F0000–U+FFFFD`
- Supplementary PUA-B: `U+100000–U+10FFFD`

Custom standard-Unicode ranges are supported mechanically, but the tool will not decide whether the semantic assignment is correct.

PUA can be legitimate for icon and symbol fonts, CJK gaiji and EUDC fonts, historical or scholarly characters, experimental scripts, legacy round trips, and closed application character sets. In every case, the meaning comes from an agreement outside Unicode.

PUA is generally the wrong mechanism for stylistic alternates, swashes, small caps, contextual forms, ordinary ligatures, localized shapes, or component glyphs. Those normally belong in OpenType features, character sequences, or unencoded glyphs.

This work is for Glyphs through Glyphs MCP; it is not a FontLab script.

Code and workflow:

- [Glyphs MCP repository](https://github.com/thierryc/Glyphs-mcp)
- [`glyphs-mcp-icon-font` skill](https://github.com/thierryc/Glyphs-mcp/blob/main/skills/glyphs-mcp-icon-font/SKILL.md)
- [Unicode assignment tool notes](https://github.com/thierryc/Glyphs-mcp/blob/main/content/contributor/unicode-assignment-tools.md)
- [Glyphs MCP command set](https://github.com/thierryc/Glyphs-mcp/blob/main/content/reference/command-set.mdx)

Unicode and font references:

- [Unicode FAQ: Private-Use Characters, Noncharacters, and Sentinels](https://unicode.org/faq/private_use.html)
- [Unicode 17, Chapter 23: Private-Use Characters](https://www.unicode.org/versions/Unicode17.0.0/core-spec/chapter-23/)
- [Unicode chart: BMP Private Use Area](https://www.unicode.org/charts/PDF/UE000.pdf)
- [Unicode chart: Supplementary Private Use Area-A](https://www.unicode.org/charts/PDF/UF0000.pdf)
- [Unicode chart: Supplementary Private Use Area-B](https://www.unicode.org/charts/PDF/U100000.pdf)
- [Glyphs Handbook: Unicode and glyph information](https://www.handbook.glyphsapp.com/en/single-page/#unicode)
- [Glyphs: Getting your glyph names right](https://glyphsapp.com/learn/getting-your-glyph-names-right)
- [OpenType specification: `cmap`](https://learn.microsoft.com/en-us/typography/opentype/spec/cmap)

I would be interested in real-world cases where a released icon font has accumulated gaps, reused values, multiple assignments, or differences from an older map.

## LinkedIn

### Post

Assigning PUA values to an icon font looks simple: start at `U+E000` and count.

The difficult part starts after the first release.

Which values are already occupied? Were deleted icons removed from the current font but still used in existing documents? Did a new glyph accidentally reuse an older assignment? Is the project treating an alternate drawing as a character when it should be an OpenType substitution?

I added a focused `glyphs-mcp-icon-font` skill to [Glyphs MCP](https://github.com/thierryc/Glyphs-mcp) to guide that workflow.

It uses two generic Unicode tools:

- review the complete font map and propose deterministic assignments;
- apply only an explicit reviewed batch, with a dry run, confirmation, stale-state checks, verification, and rollback.

For an already released font, the skill requires the previous mapping before allocating new values. Existing assignments remain authoritative, and values belonging to removed glyphs stay reserved.

The MCP tools are not limited to icons. The same mechanics can support gaiji and EUDC fonts, historical or experimental characters, legacy mappings, and other closed character sets. The icon skill is intentionally narrower: it provides workflow discipline without inventing semantics, manifests, CSS, TypeScript, Figma integration, or accessibility metadata.

The important Unicode principle is that PUA meaning comes from a private agreement among cooperating users. Unicode provides the ranges, not the meanings.

Read more:

- [`glyphs-mcp-icon-font`](https://github.com/thierryc/Glyphs-mcp/blob/main/skills/glyphs-mcp-icon-font/SKILL.md)
- [Unicode assignment notes](https://github.com/thierryc/Glyphs-mcp/blob/main/content/contributor/unicode-assignment-tools.md)
- [Unicode Private-Use FAQ](https://unicode.org/faq/private_use.html)
- [Glyphs Handbook: Unicode](https://www.handbook.glyphsapp.com/en/single-page/#unicode)

#typeDesign #fontEngineering #Unicode #GlyphsApp #MCP
