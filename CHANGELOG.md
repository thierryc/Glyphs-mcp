# Changelog

## 1.3.0 — Glyphs 4, safely—and a better Codex workflow

_July 19, 2026_

Glyphs MCP now understands the new Glyphs 4 file-format model while continuing
to work with Glyphs 3.5. It also introduces a first-class Codex marketplace
plug-in and an embedded review panel. This release is designed around one
promise: AI-assisted font work should be powerful, visible, and safe.

### The highlights

- **A first-class Codex experience.** Install the repository marketplace
  plug-in to connect Codex to Glyphs MCP, load six focused typography skills,
  and use an embedded feedback panel without duplicating global MCP setup.
- **Review before you apply.** The new panel presents server, font, glyph, and
  OpenType reports alongside guarded spacing, kerning, and handle-smoothing
  previews. Short-lived plans are revalidated before explicit confirmation;
  none of these workflows saves the font.
- **Advanced outline data stays attached.** Path edits preserve mixed shape
  order, shape groups, locked state, styling, colors, gradients, user data,
  higher-order interpolation metadata, and properties introduced by Glyphs 4.
- **Safer path round-tripping.** `get_glyph_paths` now returns
  `pathDataVersion: 2`, including shape positions and the raw node information
  needed to distinguish newer node types. Existing version-1 payloads are still
  accepted.
- **Atomic edits with a safety net.** Compatible coordinate edits happen in
  place. Topology changes clone existing paths and nodes, retain surrounding
  components and images, and restore the original layer if writing or
  verification fails.
- **Your file format is visible—and respected.** Font summaries report
  `formatVersion` and `lastSavedAppVersion`. Saving reports the format before
  and after the operation and never requests a conversion.
- **Official Glyphs 4 documentation is built in.** Documentation search now
  includes the official ObjectWrapper reference, version 3 and 4 file-format
  specifications, and the regular `.glyphs` and `fontinfo.plist` schemas.
  Results identify their source type, format version, and official URL.
- **Richer inspection for modern Glyphs files.** Path, glyph, and component
  reports now include shape-type counts, non-path shapes, group and attribute
  diagnostics, component `traverseAnchors`, raw node metadata, and focused
  compatibility warnings.
- **A hardened release pipeline.** Local publishing now fails closed around
  tests, signed tags, remote commit alignment, Developer ID signatures,
  notarization, Gatekeeper acceptance, exact release assets, and SHA-256
  checksums.

### Designed for compatibility

- Existing tool names and required arguments are unchanged.
- Legacy `get_glyph_paths` output remains valid input to `set_glyph_paths`.
- Glyphs 3.5 and Glyphs 4 are supported by the same plug-in bundle.
- Non-UI MCP clients receive the same feedback-tool information as text and
  structured output.
- Version-3 documents remain version 3 unless Glyphs itself upgrades them for a
  version-4-only feature.
- Unsafe rewrites involving node types that cannot be round-tripped are rejected
  before the layer is changed.

### Under the hood

- The bundled SDK reference now comes from the
  [official GlyphsSDK repository](https://github.com/schriftgestalt/GlyphsSDK),
  pinned to the documented Glyphs 4 revision.
- The documentation generator now lives in this repository, making reference
  builds reproducible without a private SDK fork.
- The source and Plugin Manager bundles share the same regenerated documentation
  and code.
- Codex marketplace skills are synchronized from the repository's canonical
  skill sources.
- The release is covered by metadata-preservation, rollback, schema, search,
  feedback-panel, marketplace, bundle-sync, installer, and Glyphs 3.5/4
  compatibility tests.

### Intentional scope

Version 1.3.0 adds safe compatibility, not direct authoring for every new Glyphs
4 feature. Dedicated controls for gradients, palettes, shape groups, contextual
kerning, smart-glyph axes, and higher-order interpolation remain planned for
future releases. Glyphs remains responsible for file-format conversion.

Learn more in the
[Glyphs 4 announcement](https://forum.glyphsapp.com/t/glyphs-file-format-documentation-version-4/36742)
and the
[official version 4 specification](https://github.com/schriftgestalt/GlyphsSDK/blob/Glyphs4/GlyphsFileFormat/GlyphsFileFormatv4.md).
