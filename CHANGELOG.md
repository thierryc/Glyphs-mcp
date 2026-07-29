# Changelog

## 1.5.0 — Experimental italic first passes for design exploration

_July 29, 2026_

Glyphs MCP 1.5.0 introduces Balanced italicification as an opt-in candidate
inside an explicitly experimental first-pass workflow. Its purpose is to help
a designer construct a useful emphasis companion to a Roman—not to generate
or replace a finished italic design. The expanded validation ranks Balanced
best for deterministic path geometry and promotes it as the recommended
experimental mode. Existing calls still default to Cursivy.

### The highlights

- **A reproducible mechanical starting point.** Balanced no longer depends on
  the installed Glyphs Transformations filter. It builds Raw, applies the
  pure-Python conservative correction at partial strength, interpolates those
  coordinates, then applies the requested final straight-stem compensation
  without changing topology or curve handles.
- **Design work remains visible.** Review reports anchors, components, bounds,
  metrics, topology, stem measurements, filter failures, and blocked component
  masters before any confirmed apply. Optical form, rhythm, spacing, kerning,
  alternates, and proofing remain manual design decisions.
- **Three-family Broad-Latin evidence.** A fixed 543-glyph manifest covers
  Basic Latin, Latin-1, Latin Extended, punctuation, currency, letterlike
  symbols, and number forms in pinned Inter and Noto Sans sources; pinned IBM
  Plex Sans contributes 391 Roman/Italic shared values.
- **Balanced passes the promotion gates.** All 543 Inter, 543 Noto Sans, and
  391 Plex glyphs preserved topology and source data. The test accepted 135,
  102, and 102 stem pairs respectively, with effectively zero source-width
  error after compensation. Recursive construction analysis identified and
  blocked 23 Inter and 2 Noto Sans glyphs whose component transforms do not
  commute with local shear, including Inter's reflected `d` and `q`. No unsafe
  component construction was applied.
- **High-resolution visual evidence.** Paginated 144-DPI contact and
  silhouette-difference sheets compare Roman, Raw, deterministic Partial,
  deterministic Balanced, and each family's official italic. A combined
  `4800 × 6424` story sheet shows both capacity and design limits. Official
  italics remain qualitative references, not numeric targets.

### Compatibility

- Existing calls that omit `slant_mode` continue to use Cursivy.
- Balanced remains opt-in and is the recommended experimental option, with
  `curve_strength=0.75` and `stem_compensation=1.0`. The controls are
  independent; full final compensation can make the partial interpolation
  visually subtle on accepted stems.
- Review is a genuine detached-layer dry run, confirmed apply never saves the
  font, and Raw/Cursivy behavior remains compatible with previous releases.

### Installation integrity

- The macOS installer now preserves the embedded plug-in's Developer ID
  signature instead of replacing it with an ad-hoc signature. Source, staged,
  and installed bundles must have the same CDHash and Team ID, or installation
  is rolled back.
- Terminal **Copy** mode downloads the installer ZIP for the checkout's exact
  published version and verifies its SHA-256 manifest, Developer ID identity,
  notarization ticket, Gatekeeper acceptance, version, and embedded plug-in
  signature before installing it transactionally.
- The installer's update check and update payload now resolve the latest
  non-draft, non-prerelease GitHub release. Mutable `main` source archives are
  no longer used as an update channel.
- Source-link mode remains available for trusted development checkouts, but is
  explicitly outside the signed-release and notarization guarantee.
- Public release assets no longer include the unsigned standalone plug-in ZIP.
  The release verifier simulates the final installed copy and requires its
  executable bytes and Developer ID signature to remain unchanged.
- Signed plug-in and skill payloads are stored in the installer as an immutable
  compressed-tar resource. The release build verifies its checksum and every
  extracted code signature again after signing the outer app.
- The exact archived plug-in is notarized independently before the outer app,
  and its Apple ticket is stapled into the custom `.glyphsPlugin` bundle before
  the outer app is re-signed and notarized. Both installer paths validate that
  ticket before copying the plug-in.

Read the
[experimental italic guide](content/italic-first-pass.md) and the
[Broad-Latin benchmark](content/contributor/italic-balanced-broad-latin-benchmark.md).

## 1.4.1 — Faster, bounded installer dependency setup

_July 28, 2026_

Glyphs MCP 1.4.1 makes repeated installer runs substantially smaller and more
predictable, especially with Glyphs 4 and Python 3.14.

### The highlights

- **Only the required PyObjC bindings.** The installer now installs
  `pyobjc-core` and `pyobjc-framework-Cocoa`, which provide the Objective-C
  runtime, Foundation, and AppKit used by Glyphs MCP, instead of every macOS
  framework binding.
- **Healthy dependencies are reused.** Before invoking pip, the installer
  compares every pinned requirement and verifies the runtime imports. When the
  installed environment is current, dependency installation is skipped.
- **Bounded waits and useful failures.** Dependency commands have an overall
  timeout, while pip uses bounded network timeouts and retries. Cancellation
  terminates the running command cleanly.
- **Visible Wizard progress.** The Wizard and advanced Install view show the
  current resolution, download, installation, or verification activity instead
  of leaving package details only in the Status log.
- **Consistent helper installers.** Terminal and shell installation paths no
  longer upgrade pip or request forced package reinstalls.

### Verification

- The complete local release gate passes with `401` Python tests and `82`
  macOS installer tests, followed by a successful unsigned Debug build.
- A disposable Python 3.14 environment imports `objc`, `Foundation`, `AppKit`,
  MCP, and FastMCP with `75` installed distributions, including only `2`
  PyObjC distributions. The previous full PyObjC dependency path installed
  `232` distributions, including `159` PyObjC distributions.
- The dependency preflight recognizes the completed environment and skips pip
  on the next installer run.

## 1.4.0 — A reliable plug-in UI and portable skill workflow

_July 27, 2026_

Glyphs MCP 1.4.0 expands the repository plug-in into a consistent workflow for
ChatGPT, Codex, Claude, and Cursor. It repairs embedded feedback actions,
refreshes the UI for current ChatGPT light and dark surfaces, adds guarded
authoring tools, and grows the synchronized skill bundle to eight workflows.

### The highlights

- **Feedback actions now reach the host.** OpenType Features, Refresh, and
  reviewed actions detect the host's server-tool capability, use the compatible
  OpenAI bridge when needed, and surface recoverable failures instead of
  appearing to do nothing.
- **A ChatGPT-aligned review panel.** Updated colors, type sizes, whitespace,
  focus states, action hierarchy, and responsive layouts work across light,
  dark, and narrow embedded surfaces.
- **Eight portable skills.** The canonical skill sources and packaged plug-in
  mirrors now cover connection, spacing, kerning, OpenType features, outlines
  and documentation, italic first passes, icon-font Unicode workflows, and
  Glyphs plug-in development.
- **More guarded font operations.** New tools support previewable custom
  parameters and Unicode assignment while preserving the existing confirmation
  and no-automatic-save boundaries.
- **Cross-client setup guidance.** New documentation covers the embedded
  Codex/ChatGPT UI, Claude Code and standard Claude MCP connections, and Cursor
  through `.agents/skills`, optional `.cursor/skills`, and
  `.cursor/mcp.json`.
- **Structured and text fallbacks remain first-class.** Claude, Cursor, and
  other MCP clients can use the same tools and skills even when their host does
  not render the embedded OpenAI UI.

### Verification

- The complete Python suite, Xcode installer tests, unsigned Debug installer
  build, documentation build, source/package synchronization checks, and local
  release checks cover this release.
- Browser fixtures exercise light, dark, and narrow layouts.
- Host-bridge fixtures verify successful OpenType Features and Refresh calls as
  well as recoverable unavailable and failure states.

### Remaining live QA

Live Glyphs 3.5 and Glyphs 4 compatibility checks remain a separate manual
validation step before publishing signed and notarized installer assets. This
tag does not create a GitHub Release or publish packages.

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
