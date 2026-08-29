# Variable-font audit reference

Use this checklist for a Glyphs source intended to produce an OpenType variable font.
Ordinary multiple-master static families do not automatically need every variable-font check.

## Design-space structure

- Axis tags must be four bytes, unique, and appropriate to their semantics. Record internal
  and external coordinate systems rather than assuming they are identical.
- Each axis needs a coherent minimum, default/origin, and maximum. The default must lie in
  range and correspond to a real, intended source position.
- Master coordinate tuples must be unique. Flag missing axis coordinates, unintended
  duplicate locations, and masters outside the intended design space.
- Named-instance coordinate tuples and names should be deliberate and unique. Coordinates
  must lie in the supported range; a master and instance at the same internal position must
  not disagree about their external location.
- Review Variable Font Origin, Axis Location, Axis Mappings, and virtual-master intent
  together. Mapping segments should be ordered, cover the intended extrema and default,
  and remain monotonic unless a documented nonstandard behavior is required.

## Special layers and interpolation

- Intermediate/brace layers need complete axis coordinates and compatible outlines for the
  region where their deltas participate.
- Alternate/bracket layers need valid conditions, a reachable region, a complete counterpart
  strategy, and propagation through composites that depend on the switching glyph.
- Compare component structure, path/node order, anchors, and metrics across participating
  masters and special layers. Use the dedicated compatibility skill for any repair.
- Report source features or instance filters that cannot safely vary or that Glyphs ignores
  for variable exports.

## Metadata intent and compiled proof

- Source axes and named instances should imply consistent `fvar` and STAT records. Registered
  axes should follow registered semantics; custom axes need stable tags and useful names.
- Axis mapping intent should be consistent with the expected `avar` result.
- Variable kerning belongs in GPOS, not the legacy `kern` table.
- Without a compiled binary, record `fvar`, `avar`, STAT, `gvar`/CFF2, HVAR/VVAR/MVAR,
  GDEF, GPOS variation stores, name IDs, and application behavior as `SKIP`.
- With an existing binary, validate tables and named instances, sanitize it, and sample the
  default, extrema, named positions, mapping breakpoints, and special-layer transitions.

## Trustworthy sources

- [Glyphs: creating a variable font](https://glyphsapp.com/learn/creating-a-variable-font)
- [Glyphs: intermediate layers](https://glyphsapp.com/learn/intermediate-layers)
- [Glyphs Handbook: variable-font options](https://handbook.glyphsapp.com/variable-font-options/)
- [OpenType 1.9.1 variable-font overview](https://learn.microsoft.com/en-us/typography/opentype/spec/otvaroverview)
- [OpenType 1.9.1 fvar specification](https://learn.microsoft.com/en-us/typography/opentype/spec/fvar)
- [OpenType 1.9.1 avar specification](https://learn.microsoft.com/en-us/typography/opentype/spec/avar)
- [OpenType 1.9.1 STAT specification](https://learn.microsoft.com/en-us/typography/opentype/spec/stat)
