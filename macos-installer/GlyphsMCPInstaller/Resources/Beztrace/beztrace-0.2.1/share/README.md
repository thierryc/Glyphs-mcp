# beztrace

Beztrace — /ˈbɛz.treɪs/

`beztrace` is a macOS-native tracing engine for
converting clean raster glyph images into economical, type-design-quality
cubic Bezier outlines.

[Project website](https://thierryc.github.io/beztrace/) ·
[Download stable v0.2.0](https://github.com/thierryc/beztrace/releases/tag/v0.2.0) ·
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
> Stable `0.1.1` includes the small-contour, handle-rounding, topology-safe Grid,
> convex-curve and minimum-node corrections. Its signed/notarized distribution,
> exact installed workflow and anonymous downloads are verified. See the
> [Glyphs MCP v2 integration handoff](docs/GLYPHS_MCP_V2_HANDOFF.md).
> A separately versioned [Glyphs 4 companion](https://github.com/thierryc/beztrace/blob/glyphs-v0.1.0/Companions/Glyphs/README.md)
> is independently released as signed/notarized **0.1.0/build 15**, qualified
> on Apple Silicon with Intel testing explicitly owner-waived. See the
> [companion release record](docs/GLYPHS_COMPANION_RELEASE.md).
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

[Beztrace for Glyphs](https://github.com/thierryc/beztrace/blob/glyphs-v0.1.0/Companions/Glyphs/README.md) adds **Path → Beztrace…** to trace a native canvas image
at its existing placement, with reversible native path insertion. A separate
Python API supports automatic image placement for coding agents.
Its [signed 0.1.0/build 15 release](https://github.com/thierryc/beztrace/releases/tag/glyphs-v0.1.0)
is versioned independently of the engine. Native qualification covers macOS
14.6.1 arm64, Glyphs 4.1.1/build 4108 and Python 3.14.6. Intel native execution
is untested and explicitly owner-waived; universal signature verification does
not establish Intel runtime qualification. See the [release record](docs/GLYPHS_COMPANION_RELEASE.md).

Stable **0.1.1** incorporates all four development engine corrections while
retaining JSON schema v1, path data version 2, and the public Swift API.
The [development verification history](docs/SMALL_CONTOUR_FIX.md) records those fixes.
Companion build 15 accepts stable 0.1.1; older installed companions must continue
using a supported engine until separately upgraded. The standalone distribution
does not include the separately distributed native Glyphs companion.

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

## Engine 0.2.1 and companion 0.2.0 preparation

The working engine is **0.2.1** and the companion is **0.2.0/build 25**. This
includes verified hybrid fitting, joint smoothing and the grouped four-mode
sidebar. Local unsigned preparation remains separate from final qualification,
signing and notarization. The published standalone engine 0.2.0 and all earlier
release assets retain their original bytes. See the [release preparation record](docs/RELEASE_0.2.1.md).

## Compatible master matching preview

[Download 0.2.0-dev.1](https://github.com/thierryc/beztrace/releases/tag/v0.2.0-dev.1)
for detached matching of two images, an outline plus an image, or two outlines.
Provide your two glyph sources, run matching, and review the compatible outlines
and intermediate weights before importing them into your font editor.

```sh
./bin/beztrace match-pair JOB.json --output-directory RESULTS --json-errors
```

The archive includes runnable R/Y examples, schemas and visual review reports.
A vector reference stays exact by default; shared growth requires explicit limits.
This is an **unsigned development preview**. Native matching UI, font application
and stable release qualification remain separate. See [preview status](docs/RELEASE_0.2.0-dev.1.md)
and [configuration](docs/PAIR_WORKFLOW.md).

The working source also provides an explicit [joint smoothing step](docs/JOINT_SMOOTHING.md)
for already-compatible outlines, preserving the reference and node structure
under the original-source error limit. Use a locally built engine advertising
`jointSmoothingVersion: 1`; this addition is not a newly published release.
The working companion 0.2.0/build 25 integrates this as **Smooth compatible joins**
using matching capability `matchSmoothingVersion: 1`, with native HOI correction
in the contextual Interpolation group. See the [companion development workflow](Companions/Glyphs/README.md).

## Install the published standalone release (0.2.0)

Download `beztrace-0.2.0.pkg` and `SHA256SUMS` from the
[v0.2.0 release](https://github.com/thierryc/beztrace/releases/tag/v0.2.0),
verify the checksum, then install the signed, notarized package:

```sh
shasum -a 256 -c SHA256SUMS
sudo installer -pkg beztrace-0.2.0.pkg -target /
beztrace --version
```

The installer places the universal executable under
`/Library/Application Support/beztrace/bin` and exposes it as
`/usr/local/bin/beztrace`. The released Glyphs companion requires its separately
supported 0.1.1 engine; installing the CLI does not upgrade that consumer.
Use the standalone ZIP when retaining the existing shared engine. See the
[release guide](docs/RELEASE.md) and [0.2.0 record](docs/RELEASE_0.2.0.md).

## Repository policy

The `main` branch holds released, reviewed source. Future implementation uses
an explicitly authorized `lit/` branch and returns to `main` only after its
documented gates pass.

## Project documents

- [Master matching development contract](docs/MASTER_MATCHING.md)
- [Standalone pair matching workflow](docs/PAIR_WORKFLOW.md)
- [Implementation directive](docs/IMPLEMENTATION_DIRECTIVE.md)
- [Requirements](docs/REQUIREMENTS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Interfaces](docs/INTERFACES.md)
- [Porting and licensing](docs/PORTING_AND_LICENSE.md)
- [Port map](docs/PORT_MAP.md)
- [Quality gates](docs/QUALITY_GATES.md)
- [Local checks (no GitHub Actions)](docs/TESTING.md)
- [Roadmap](docs/ROADMAP.md)
- [Milestone 6 viability review](docs/VIABILITY_REVIEW.md)
- [Release and verification](docs/RELEASE.md)

## Agent skills

Two generic source skills cover [image vectorization](skills/beztrace-vectorize-image/SKILL.md)
and [compatible master matching with point limits](skills/beztrace-match-masters/SKILL.md).
Matching requires the optional development capability; ordinary tracing remains
standalone. Their [Glyphs MCP skill catalog handoff](docs/BEZTRACE_SKILLS_CATALOG_PLAN.md)
describes planned app packaging and qualification; it does not change the app.

## License

The project is dual-licensed under the Apache License 2.0 or the MIT
License. Ported files must preserve upstream copyright and SPDX attribution.
See [Porting and licensing](docs/PORTING_AND_LICENSE.md) and
[third-party notices](THIRD_PARTY_NOTICES).
