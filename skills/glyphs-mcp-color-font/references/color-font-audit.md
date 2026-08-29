# Color-font audit reference

Use this source-level checklist only when the font intentionally contains color artwork.
Record the mechanism, target formats, and evidence boundary before assigning severity.

## Source inventory

- Identify palette/COLR-style layers, native Color layers, SVG layers, sbix/iColor
  strikes, and layered color masters separately. Similar UI labels do not make these
  mechanisms interchangeable.
- Record all palette definitions and names. Every palette must have the same number of
  entries; every layer reference must be in range. A missing optional label is not the
  same defect as a missing color entry.
- For each intended color glyph, record base glyph, master, layer order, palette index,
  width, export state, and whether the referenced SVG or bitmap payload is present.
- Flag empty color layers, broken external SVG references, malformed SVG payloads,
  duplicate strikes at the same size, and inconsistent strike coverage.
- Compare advance widths and positioning across color layers. Shared artwork must not
  drift because one layer has unrelated metrics.

## Fallbacks and mixed mechanisms

- COLR base glyphs and OpenType-SVG glyphs still need corresponding outline glyphs.
  Confirm that each intended color glyph has a usable monochrome fallback rather than
  assuming the color table replaces ordinary outlines.
- An empty fallback may be intentional only when the supported platform contract is
  documented and tested. Otherwise report missing readable fallback artwork.
- When multiple color mechanisms are enabled, verify that the combination is deliberate,
  the same glyph repertoire is intended for each, and instance custom parameters do not
  accidentally suppress or multiply tables.
- Do not infer CBDT/CBLC support from sbix layers. They are distinct bitmap formats.

## Evidence levels

1. **Source verified:** palettes, layers, payload references, metrics, and export controls
   were inspected in the Glyphs document.
2. **Export review verified:** the typed source review completed, subject to every
   limitation it reports.
3. **Binary verified:** an existing output was parsed and sanitized, and its actual color
   tables, palette references, glyph coverage, fallbacks, and target rendering were tested.

If level 3 evidence is absent, mark compiled table structure and rendering as `SKIP`.
Glyphs MCP v2 currently rejects color special layers in source-bundle compilation; preserve
that result as a coverage gap rather than claiming the color source is export-safe.

## Trustworthy sources

- [Glyphs Handbook: COLR/CPAL fonts](https://handbook.glyphsapp.com/color-fonts/colr-cpal/)
- [Glyphs Handbook: SVG color fonts](https://handbook.glyphsapp.com/color-fonts/svg/)
- [Glyphs: creating an SVG color font](https://glyphsapp.com/learn/creating-an-svg-color-font)
- [OpenType 1.9.1 COLR specification](https://learn.microsoft.com/en-us/typography/opentype/spec/colr)
- [OpenType 1.9.1 CPAL specification](https://learn.microsoft.com/en-us/typography/opentype/spec/cpal)
- [OpenType 1.9.1 SVG specification](https://learn.microsoft.com/en-us/typography/opentype/spec/svg)
- [OpenType 1.9.1 sbix specification](https://learn.microsoft.com/en-us/typography/opentype/spec/sbix)
