# Changelog

## 0.1.1 source — 2026-10-04 (binary publication pending)

- Promote the four development engine corrections to a stable standalone release.
- Preserve small closed contours and meaningful convex curvature.
- Reject unsafe handle rounding and keep safe no-grid geometry when Grid would
  invalidate topology, with deterministic fallback warnings.
- Guarantee at least three on-curve nodes by exact subdivision of two-segment loops.
- Retain JSON schema v1, pathDataVersion 2, and the public Swift API.
- Prepare universal distribution and SPDX SBOMs. The executable is Developer ID
  signed; installer signing, Apple notarization and installation verification
  remain pending before binary publication.
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
