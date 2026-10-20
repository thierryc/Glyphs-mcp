# Changelog

## Engine 0.2.1 / companion 0.2.0 — preparation, not yet published

- Retain standalone matching of two images, image to reference, and two outlines.
- Add independently verified Levien-first fitting with refined least-squares fallback.
- Add efficient joint smoothing within the original error limit, preserving the
  reference, on-curves and compatible node structure. Graph selection is deferred.
- Add the four-mode Glyphs companion with contextual sidebar groups, bounded point
  growth, explicit correspondence, native HOI opt-in and hint-preserving application.
- Retain schema v1 and pathDataVersion 2; add exact engine 0.2.0/0.2.1 compatibility in
  companion build 25 while retaining earlier supported engine versions.
- Stage local universal packages; clean-source/native acceptance, signed and
  notarized distribution, installation and publication remain separate gates.

## 0.2.0 — 2026-10-12

- Publish standalone master matching with unchanged preview geometry and fixtures.
- Distribute the signed/notarized universal ZIP and installer, schemas and R/Y examples.
- Qualify the standalone package independently; native font application and the
  companion remain outside the engine release. Preserve the tag and asset bytes.

## 0.1.1 — 2026-10-05

- Promote the four development engine corrections to a stable standalone release.
- Preserve small closed contours and meaningful convex curvature.
- Reject unsafe handle rounding and keep safe no-grid geometry when Grid would
  invalidate topology, with deterministic fallback warnings.
- Guarantee at least three on-curve nodes by exact subdivision of two-segment loops.
- Retain JSON schema v1, pathDataVersion 2, and the public Swift API.
- Publish checksum-verified universal ZIP/PKG, manifest and SPDX SBOMs after
  Developer ID signing, Apple notarization, Gatekeeper and installation checks.
- Name Beztrace 0.1.1 in the installer title, welcome and completion pages.
- Bind CLI process tests to their own build, preserving historical artifacts.
- Companion source build 12 adds engine compatibility; it remains an unsigned,
  separately qualified development product and is not a stable release asset.

## 0.1.1-dev.4 — local development candidate

- Preserve meaningful curvature on small, consistently convex contours when
  cleanup would otherwise replace a cubic quadrant with a straight chord.
- Exclude intentional flats, corners, inflections, concave paths, large
  contours, rectangles and pills from the correction.
- Add multi-size, rotated-oval and intentional-structure regressions while
  preserving the complete 100-image corpus geometry.
- Guarantee at least three on-curve nodes on every valid closed output by
  subdividing a two-segment loop without changing its Bézier geometry.
- Add Glyphs companion build 11 with dev.4 selection and compatibility.

## 0.1.1-dev.3 — local development candidate

- Make Grid cleanup validity-preserving: contours whose snapped candidates
  would collapse, self-intersect, or otherwise fail final validation retain
  their fully cleaned no-grid geometry.
- Reuse the final outline validator for candidate acceptance, preserve hard
  failures for invalid no-grid geometry, and report deterministic fallback
  warnings through the existing result contract.
- Add the reported Grid 8 profile and boundary-profile corpus regressions.
- Add Glyphs companion build 10 with dev.3 selection and warning display, plus
  a 300-point native panel with Preset outside Advanced Options, Threshold inside
  it, a right-aligned disclosure, stable top-edge resizing and inline validation.

## 0.1.1-dev.2 — local development candidate

- Reject deterministic handle-rounding candidates that would violate the final
  handle-reach validator, preserving the preceding safe fitted handles.
- Add a regression for Accuracy 3, Smoothing 0.7 and Grid 1 on the committed
  sparkle fixture. Public API, schema and path-data versions are unchanged.

## 0.1.1-dev.1 — development prerelease

- Preserve small closed contours through smoothing and fitting, including
  loops whose endpoints coincide and contours formed by two cubic segments.
- Compute winding from cubic geometry instead of the endpoint polygon.
- Add synthetic regressions; retain JSON schema v1 and pathDataVersion 2.
- Glyphs companion build 6 accepts this local engine and released 0.1.0,
  verifying that result and executable versions match.

This development prerelease has no Developer ID signing, notarization or
automatic system installation. See `docs/SMALL_CONTOUR_FIX.md` for local verification.

## 0.1.0 — 2026-08-27

First standalone release.

- Added deterministic PNG/JPEG preparation for clean monochrome glyphs and
  symbols.
- Added subpixel contour extraction, structural planning, constrained cubic
  fitting, raster refinement, typographic cleanup, and fail-closed validation.
- Added the neutral Swift API, JSON schema v1, and `pathDataVersion 2`.
- Added transform-free baked SVG and Y-up preserve SVG modes.
- Added `trace`, `batch`, and `inspect` command-line workflows.
- Added universal Apple Silicon and Intel distribution, Developer ID signing,
  Apple notarization, SPDX SBOMs, checksums, and package installation.

Glyphs.app and Glyphs MCP integration are deliberately not included. They are
future consumers of the neutral JSON contract.

Native qualification correction (build 25): evaluate native metadata getters, preserve custom hint user data across native copies and recovery, and prepare detached hint copies before attachment. Native hinted Undo remains under qualification.
