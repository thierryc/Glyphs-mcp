# beztrace

Beztrace — /ˈbɛz.treɪs/

`beztrace` is a macOS-native tracing engine for
converting clean raster glyph images into economical, type-design-quality
cubic Bezier outlines.

[Project website](https://thierryc.github.io/beztrace/) ·
[Download stable v0.2.1](https://github.com/thierryc/beztrace/releases/tag/v0.2.1) ·
[Release verification](docs/RELEASE.md)

> [!IMPORTANT]
> The current stable engine is **0.2.1**. The optional Glyphs 4 companion is
> **0.2.0/build 25**. Both are published as universal arm64 + x86_64 distributions,
> Developer ID signed and Apple-notarized; the engine installer has a stapled ticket.
> See the [current release qualification](docs/RELEASE_0.2.1.md) and
> [companion release record](docs/GLYPHS_COMPANION_RELEASE.md).
> Native Intel execution is untested and explicitly owner-waived for these versions;
> Rosetta results are separate evidence. The engine runs without Glyphs or Python.
> Glyphs MCP setup and adapter integration remain separate work.

The next universal release is being prepared as engine **0.2.2** and companion
**0.2.1/build 26**. See [its preparation and qualification record](docs/RELEASE_0.2.2.md).
The published stable versions above remain unchanged until qualification finishes.

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

[Beztrace for Glyphs](https://github.com/thierryc/beztrace/releases/tag/glyphs-v0.2.0)
**0.2.0/build 25** adds four native tracing and matching modes, grouped settings,
verified fitting and optional compatible smoothing. Install the separately
released **engine 0.2.1**, then open the plugin in Glyphs and relaunch.
Native qualification covers Apple Silicon / Glyphs 4.2/build 4202, including
signed Apply/Undo/Redo and installation/update/rollback/removal/reinstallation.
Native Intel remains **untested, explicitly owner-waived** for these versions.
See the [companion release record](docs/GLYPHS_COMPANION_RELEASE.md).

Stable engine **0.2.1** retains the standalone matching introduced in 0.2.0 and
adds independently verified fitting and smoothing, retaining JSON schema v1 and
path data version 2. The standalone CLI does not install or upgrade the
companion. For older companion versions, check the compatibility notes in the
[release guide](docs/RELEASE.md) before upgrading a shared engine.

## Supported inputs and platforms

- macOS 13 or later, Swift 6, `arm64` and `x86_64`.
- Clean, high-resolution monochrome or alpha glyph images.
- PNG and JPEG input by path or standard input.
- Canonical neutral geometry plus explicit caller-supplied placement.
- Versioned JSON and SVG output.
- Standalone two-master matching of clean images and line/cubic outlines, with
  explicit correspondence, fit tolerance, node limits and interpolation review.
- No photography, arbitrary multicolor segmentation, UFO/GLIF writing, learned
  models, network access, or Glyphs.app dependency.

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

## Engine 0.2.1 and companion 0.2.0 — released 2026-10-18

Both distributions are universal arm64 + x86_64, Developer ID signed and
Apple-notarized. The engine PKG has a validated stapled ticket. The fitting
pipeline uses Levien-style proposals with refined least-squares fallback and an
independent original-source verifier. Efficient joint smoothing preserves the
reference, on-curves and node structure within the same error limit. Graph
selection remains deferred.

All 27 local checks pass. The same 12 smoothing cases retain exact geometry,
reports, bounds and refusal limits; all 18 pair jobs match across native arm64
and Rosetta. Signed installation, rollback, removal and reinstallation pass in
the owned macOS 14.6.1 arm64 VM. Signed companion UI Undo/Redo is exact on
Glyphs 4.2/build 4202; earlier unchanged Python source qualification includes
fresh-file exchange and 603 compiled interpolation checks. Native Intel is
untested and explicitly owner-waived, with Rosetta recorded separately.

See the [release qualification](docs/RELEASE_0.2.1.md) and
[build 25 qualification](Companions/Glyphs/QUALIFICATION_BUILD25.md).

## Standalone compatible master matching

[Download stable 0.2.1](https://github.com/thierryc/beztrace/releases/tag/v0.2.1)
for detached matching of two images, an outline plus an image, or two outlines.
Provide two glyph sources, run matching, and review the compatible outlines and
intermediate weights before importing them into your font editor.

```sh
./bin/beztrace match-pair JOB.json --output-directory RESULTS --json-errors
```

The archive includes runnable R/Y examples, schemas and visual reviews.
A vector reference stays exact by default; shared growth requires explicit limits.
See [configuration](docs/PAIR_WORKFLOW.md) and the explicit
[joint smoothing step](docs/JOINT_SMOOTHING.md). Companion 0.2.0/build 25 exposes
this as **Smooth compatible joins**. For already-compatible outlines, choose
**Review existing structure** to retain the existing correspondence.

## Install the published standalone release (0.2.1)

Download `beztrace-0.2.1.pkg` and the release assets from the
[v0.2.1 release](https://github.com/thierryc/beztrace/releases/tag/v0.2.1),
verify `SHA256SUMS`, then install the signed, notarized package:

```sh
shasum -a 256 -c SHA256SUMS
sudo installer -pkg beztrace-0.2.1.pkg -target /
beztrace --version
```

The universal executable is installed under
`/Library/Application Support/beztrace/bin`, exposed as `/usr/local/bin/beztrace`.
Use the ZIP to run separately while retaining an older shared engine. Installing
the CLI does not upgrade an existing companion. See the [release guide](docs/RELEASE.md).

## Repository policy

The `main` branch holds released, reviewed source. Future implementation uses
an explicitly authorized `lit/` branch and returns to `main` only after its
documented gates pass.

## Project documents

- [Master matching contract](docs/MASTER_MATCHING.md)
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

## Use with coding agents

Codex and Claude Code can run the installed **Beztrace 0.2.1** CLI on your Mac
to trace images, match masters and review results. Beztrace itself needs no MCP
server or API key; your coding agent uses its usual account and permissions.

Install the complete folders for [image tracing](skills/beztrace-vectorize-image/SKILL.md)
and [master matching](skills/beztrace-match-masters/SKILL.md) in your agent's
skills directory:

| Agent | Personal skills directory | Invoke in a prompt |
| --- | --- | --- |
| Codex CLI / IDE | `~/.agents/skills/` | `$beztrace-vectorize-image` or `$beztrace-match-masters` |
| Claude Code | `~/.claude/skills/` | `/beztrace-vectorize-image` or `/beztrace-match-masters` |

For example: “Use Beztrace to match this Bold image to my Regular outline.
Keep the reference exact, retain its node structure, use a 1-unit tolerance
at 1000 UPM, and show the comparison report and intermediate weights.”

The [coding-agent setup guide](docs/CODING_AGENTS.md) includes installation
commands, prompts for both agents, placement settings and result checks.
Other agents with local shell access can use the same documented CLI and JSON
contracts. Agent-driven application in Glyphs additionally requires the optional
native companion and an authorized Glyphs scripting connection; installing these
skills alone does not provide that connection. The separate
[Glyphs MCP catalog handoff](docs/BEZTRACE_SKILLS_CATALOG_PLAN.md) records planned
app packaging.

## License

The project is dual-licensed under the Apache License 2.0 or the MIT
License. Ported files must preserve upstream copyright and SPDX attribution.
See [Porting and licensing](docs/PORTING_AND_LICENSE.md) and
[third-party notices](THIRD_PARTY_NOTICES).
