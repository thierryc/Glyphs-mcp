# beztrace

`beztrace` is a macOS-native tracing engine for
converting clean raster glyph images into economical, type-design-quality
cubic Bezier outlines.

[Project website](https://thierryc.github.io/beztrace/) ·
[Download stable v0.1.0](https://github.com/thierryc/beztrace/releases/tag/v0.1.0) ·
[Release verification](docs/RELEASE.md)

> [!IMPORTANT]
> Reference capture, the Swift tracing pipeline, neutral public API, placement,
> versioned JSON/SVG, and the standalone command-line tool are implemented and
> tested. The 100-image release-candidate input corpus is frozen and passes
> automatic topology and determinism checks, and the project owner accepted all
> 100 reviewed traces. The optimized test matrix, performance, memory,
> cross-architecture, fuzz, and packaged-workflow gates pass. The current
> Milestone 6 viability review approves merge: the universal executable and
> installer are Developer ID signed, Apple-notarized, installed, and verified
> through a real standalone JSON/SVG workflow.
> Source version `0.1.1` incorporates the small-contour, handle-rounding,
> topology-safe Grid and convex-curve corrections. Its engineering checks pass.
> The binary release is pending installer Keychain approval, explicit Apple
> notarization authorization, and installation verification. The current
> downloadable stable release remains `0.1.0`.
> A separately versioned [Glyphs 4 companion](Companions/Glyphs/README.md) is
> under development in this repository; its native qualification is pending.
> Glyphs MCP setup and adapter integration remain separate work.

## Intended product

The standalone engine is split into two reusable layers:

- `BezierTraceCore`, a Swift library that owns image preparation, tracing,
  placement, validation, and the neutral public result contract.
- `beztrace`, a standalone command-line tool exposing JSON/SVG tracing to local
  shell, batch, CI, and automation workflows. A signed and notarized universal
  release is available for installation.

beztrace is intended to become a standalone companion engine for
[Glyphs MCP](https://ap.cx/tools/glyphs-mcp/):
it will turn raster glyphs and symbols into neutral, versioned path data that a
future Glyphs MCP adapter can apply through the existing path-mutation tools.
Glyphs MCP is a consumer, not a runtime dependency or target in this product.
The standalone viability gate in [Quality gates](docs/QUALITY_GATES.md) has
passed. The optional native companion consumes the released CLI and neutral JSON
contract. Glyphs dependencies stay in `Companions/Glyphs`; they are not Swift
package or CLI dependencies. Future Glyphs MCP integration remains separate.

## Optional Glyphs companion

[Beztrace for Glyphs](Companions/Glyphs/README.md) adds **Path → Beztrace…** to trace a native canvas image
at its existing placement, with reversible native path insertion. A separate
Python API supports automatic image placement for coding agents.
Its unsigned development artifact is versioned independently of the engine.
Full native UI qualification and signed distribution remain pending.

Source **0.1.1** incorporates all four development engine corrections while
retaining JSON schema v1, path data version 2, and the public Swift API.
The [development verification history](docs/SMALL_CONTOUR_FIX.md) records those fixes.
Companion source build 12 accepts 0.1.1; older installed companions must continue
using a supported engine until separately upgraded. The standalone distribution does
not include the unsigned, native-unqualified Glyphs companion.

## Standalone v1 boundaries

- macOS 13 or later, Swift 6, `arm64` and `x86_64`.
- Clean, high-resolution monochrome or alpha glyph images.
- PNG and JPEG input by path or standard input.
- Canonical neutral geometry plus explicit caller-supplied placement.
- Versioned JSON and SVG output.
- No photography, arbitrary multicolor segmentation, variable-font master
  matching, UFO/GLIF writing, learned models, network access, or Glyphs.app
  dependency in v1.

The implementation is a one-time derivative Swift port of img2bez
commit `23073ca08ecdac61ad0e838bfae49a590bc2c7cc`, licensed under
`Apache-2.0 OR MIT`. It will not automatically track later upstream changes.

## Local command-line use

Build and trace without installing anything:

```sh
swift build --configuration release
swift run --configuration release beztrace trace input.png --format json
swift run --configuration release beztrace trace input.png --format svg --output outline.svg
swift run --configuration release beztrace trace input.png --format svg \
  --svg-transform preserve --output outline-y-up.svg
```

SVG defaults to transform-free, visually upright coordinates for Sketch,
Illustrator, Figma, and similar consumers. Use `--svg-transform preserve` when
the SVG path itself must remain in the same y-up coordinates as JSON and be
rendered through an SVG group transform. JSON remains the authoritative
neutral path format for the future Glyphs MCP companion adapter.

Use `beztrace --help` for batch, inspection, tracing, placement, and SVG
transform options.
JSON schema v1 is committed at
[`Schemas/trace-result-v1.schema.json`](Schemas/trace-result-v1.schema.json).

## Install the current stable release (v0.1.0)

Download `beztrace-0.1.0.pkg` and `SHA256SUMS` from the
[v0.1.0 release](https://github.com/thierryc/beztrace/releases/tag/v0.1.0),
verify the checksum, then install the notarized package:

```sh
shasum -a 256 -c SHA256SUMS
sudo installer -pkg beztrace-0.1.0.pkg -target /
beztrace --version
```

The installer places the universal executable under
`/Library/Application Support/beztrace/bin` and exposes it as
`/usr/local/bin/beztrace`. See the [release and verification guide](docs/RELEASE.md)
for assets, signatures, SBOMs, and smoke tests.

## Repository policy

The `main` branch holds released, reviewed source. Future implementation uses
an explicitly authorized `lit/` branch and returns to `main` only after its
documented gates pass.

## Project documents

- [Implementation directive](docs/IMPLEMENTATION_DIRECTIVE.md)
- [Requirements](docs/REQUIREMENTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Interfaces](docs/INTERFACES.md)
- [Porting and licensing](docs/PORTING_AND_LICENSE.md)
- [Port map](docs/PORT_MAP.md)
- [Quality gates](docs/QUALITY_GATES.md)
- [Test workflow](docs/TESTING.md)
- [Roadmap](docs/ROADMAP.md)
- [Milestone 6 viability review](docs/VIABILITY_REVIEW.md)
- [Release and verification](docs/RELEASE.md)

## License

The project is dual-licensed under the Apache License 2.0 or the MIT
License. Ported files must preserve upstream copyright and SPDX attribution.
See [Porting and licensing](docs/PORTING_AND_LICENSE.md) and
[third-party notices](THIRD_PARTY_NOTICES).
