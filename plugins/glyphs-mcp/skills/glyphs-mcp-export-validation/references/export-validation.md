# Export-validation reference

Choose evidence deliberately. A source review cannot prove binary table correctness, and a
binary validator cannot prove that the current unsaved Glyphs document produced the artifact.

## Source-readiness mode

- Record document fingerprint, intended instance, output format, variable/static target,
  destination, and overwrite policy.
- Preserve every structured export blocker and warning, including unsupported special layers,
  feature compilation, incompatible outlines, instance configuration, and destination conflict.
- Do not create an output merely to make an audit more complete. Export is a separate effect
  with its own destination and approval boundary.

## Existing-binary mode

- Record path, size, SHA-256, modification time, flavor, outline format, and validator versions.
- Run OTS when installed. An unavailable sanitizer is `SKIP`; an OTS rejection is a blocker.
- Run the FontBakery universal profile by default. Preserve FAIL and ERROR as blockers unless
  the project has a documented, target-approved exception. Preserve WARN and INFO separately.
- Run a Google Fonts, Adobe, Microsoft, or other distributor profile only when that distributor
  is an actual target; profile policies are not interchangeable.
- Inspect table directory, cmap coverage, glyph 0, names, OS/2 and head style bits, PostScript
  names, version strings, vertical metrics, embedding flags, and outline/table consistency.
- For variable binaries, inspect `fvar`, `avar`, STAT, variation stores, named instances, and
  representative locations. For color binaries, use the color-font skill's binary evidence
  matrix.

## Release comparison

- When a prior-release artifact is supplied, compare family/style identity, mappings, glyph
  order where stability matters, metrics, kerning/feature behavior, axes and instances, tables,
  hinting policy, file size, and validator result changes.
- Distinguish intentional product changes from unexplained regressions. Never compare against
  an invented or downloaded baseline that the user did not identify as authoritative.

## Result accounting

Report each check as PASS, WARN, FAIL, ERROR, or SKIP and include the exact artifact. State
which target applications and rendering engines were not tested. Zero recorded failures is
not release approval when required checks were skipped.

## Trustworthy sources

- [OpenType 1.9.1 specification](https://learn.microsoft.com/en-us/typography/opentype/spec/)
- [OpenType recommendations](https://learn.microsoft.com/en-us/typography/opentype/spec/recom)
- [OpenType Sanitizer](https://github.com/khaledhosny/ots)
- [FontBakery documentation](https://fontbakery.readthedocs.io/)
- [FontBakery profile documentation](https://github.com/fonttools/fontbakery/blob/main/docs/source/developer/writing-profiles.md)
- [Glyphs Handbook: exporting fonts](https://handbook.glyphsapp.com/export/)
