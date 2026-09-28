# Beta 8 milestone 2 — scope-proportional typed preparation

Status: **complete locally. Implementation, regression/native parity, all 140
benchmark runs and actual-editor/installed Codex qualification pass.** The later
[joint editor report](../beta8-milestone3/editor-qualification.md) closes the
previous installation gate and records the additional editor-discovered fix.

## Changes

- Named width preparation uses exact native glyph lookups, preserving native
  font order and all stored layers of each requested glyph. It does not scan
  unrelated glyphs twice. Missing names still fail the entire request, and
  preparation does not manufacture master layers or backgrounds.
- Color preparation copies glyph metadata with Glyphs' layer-excluding copy
  option. It retains the existing patch, report, metadata hashes and selective
  recovery. Custom colors are checked before copying: native evidence shows
  that this copy drops custom color objects. Unsupported copying fails explicitly.
- Outline preparation, application and snapshot restoration share a nullable
  node-name setter. The native selector preserves `None`; the Python wrapper
  stringifies it. Named, empty and absent values remain distinct, with original
  node objects preserved. No snapshot representation was added.

Saved/clean prerequisites, exact application guards, selective recovery,
background preservation, native Undo/Redo, worker routing for other operations,
limits and twelve public tools remain. This does not make the entire workflow
proportional to selected targets: saved-source validation still reads the whole
baseline, and color application/recovery retain their existing serialization.

## Tests-first evidence

- [Initial regressions](tests-before.txt): eight expected failures, two passes.
  They expose full glyph copying, unrelated glyph enumeration and absent-name
  normalization. [The additional nullable-name parity test](tests-clear-name-before.txt)
  failed against retained outline preparation before its shared setter was fixed.
- [Focused checks](tests-focused.txt): 90 pass, including missing/API failures,
  custom colors, metadata conflict guards, exact stored-layer scope, fractional
  coordinates, stale requests, native-route errors without worker fallback and
  identity-preserving recovery.
- [Full suite](final-tests.txt): **2,307 passed, two skipped**. Skips are the
  unavailable Copilot CLI and opt-in dependency-install matrix. Existing native
  runtime dependencies are reused. Warnings are existing dependency deprecations.
- The [native pre-change probe](native-probe-before.txt) reproduces the empty
  node name and proves the native nil setter. It also records the custom-color
  omission in metadata-only copies, which preparation explicitly rejects.
- Native parity checks in [.glyphs](native-complete-glyphs.json) and
  [.glyphspackage](native-complete-glyphspackage.json) compare the retained worker
  and candidate native route, exact patches/reports, two masters, foreground and
  background outlines, components, fractional coordinates, missing backgrounds,
  selective recovery and native Undo/Redo. Every standard palette color, clearing
  and custom-label rejection also pass with identical patches/reports. These are disposable standalone native
  documents; they are not presented as actual editor Save tests.

## Performance evidence

The final matrix uses five fresh processes per case and identical prebuilt
fixtures for the frozen milestone 1 runtime and candidate. It is a comparison
against the current native route, not v1 or historical worker timings.

All **140 measured runs pass**, five repetitions per case and route. Full
medians/ranges and stage timings are in the [comparison matrix](matrix/README.md)
and [machine-readable summary](matrix/summary.json). Selected medians in seconds:

| Task | Format | Preparation before → after | Prepare + apply/poll before → after |
| --- | --- | ---: | ---: |
| Color 100 glyphs | `.glyphs` | 9.424 → 0.446 | 27.618 → 19.189 |
| Color 100 glyphs | `.glyphspackage` | 9.515 → 0.460 | 27.708 → 18.810 |
| Width, 1 named layer | `.glyphs` | 0.607 → 0.069 | 0.692 → 0.144 |
| Width, 100 named layers | `.glyphs` | 0.622 → 0.079 | 0.720 → 0.138 |
| Width, 1,000 named layers | `.glyphs` | 0.588 → 0.199 | 1.035 → 0.657 |
| Width, 4,096 named layers | `.glyphs` | 0.666 → 0.640 | 2.449 → 2.399 |
| Width, 4,096 named layers | `.glyphspackage` | 1.017 → 0.854 | 3.310 → 2.760 |

Color preparation improves about 21× at 100 targets, but the measured edit total
improves about 1.4–1.5× because application and recovery retain their existing
costs. Small named-width requests benefit most; near-full-font requests improve
less. Peak process memory is essentially unchanged at the largest fixture:
maximum 723.2 MiB before / 722.4 MiB after, including fixture and verification.
Maximum scheduled preparation chunk drops from 267.8 ms to 36.8 ms, but the
longest scheduled work across all stages is still 843.1 ms after (942.4 ms
before). No universal chunk-budget or UI-responsiveness guarantee is implied.

**Measured regression:** one-color `.glyphs` results rise from 0.404 to 0.527
seconds overall, although preparation improves. The [before trace](polling-before.json)
and [after trace](polling-after.json) locate the delay: native application takes
about 181/175 ms, while the interval from native completion to workflow result
grows from 63 to 253 ms. Faster preparation shifts completion relative to the
existing 250 ms supervisor tick; applying-state reads wait for that supervisor.
The package one-color case improves (0.683 → 0.599 seconds). This explains the
repeatable small-case regression; it is retained as a conversation/polling
follow-up, not hidden by the bulk averages or fixed through extra milestone work.

Colors select 1/10/100 glyphs in a 501-glyph family with two masters and four
triangular contours on foregrounds and the Regular background. Widths select
1/100/1,000/4,096 dispersed named glyphs in a 5,000-glyph font with four contours
in foreground and background. Requests list targets in reverse order. Every run
checks untouched persisted contents, native Undo/Redo and selective recovery.

[Preliminary evidence](preliminary/) is excluded from the final matrix. It used
32-contour color fixtures and a slower Python-node verification routine; an
intermediate verification rewrite failed because it used an unavailable native
property-list selector. The final harness uses the actual supported selector and
native persisted contents. Earlier observations and the failure are retained,
not combined with the final comparison. The first width check also failed
because it assumed background widths were independent. Native evidence shows
that the background width follows its owning foreground. The final check verifies
that inherited width explicitly while comparing all other persisted contents;
both runtimes retain that existing behavior. Ordinary desktop activity and some
source checks occurred during qualification; there was no exclusive CPU
reservation. Peak memory is isolated per fresh process, not incremental memory
attributable only to the edit. No universal responsiveness guarantee is implied.

## Build and installation

The MCP candidate is rebuilt into the established `build/simple-native-scripting`
target, reusing the verified bundled runtime. [Source/build identities](candidate-identity.json)
and [build manifest](build.json) record the candidate. [Byte verification](build-verification.json)
confirms all 112 runtime Python source/built copies match. The frozen baseline
and final shared benchmark harness are checked in [benchmark identity](benchmark-identity.json). Skill mirrors are synchronized,
and the package check retains eleven skills, twelve tools and both architectures.

At the original handoff, installed verification was pending: Dactylotype was discovered open and dirty.
It was rechecked after the benchmark and remains dirty with the same binding.
No save, close or restart was performed. The user was asked how to preserve that
unsaved work before the already-authorized installation/relaunch. Existing
companions and settings must remain unchanged; only MCP is to be updated.
Disposable [editor fixtures](editor-fixtures.json) in both formats are ready for
installed width/color/outline checks, exact unnamed-node Undo/Redo and selective
recovery; they have not been opened in the editor.

That historical boundary is now superseded by the joint editor report above.
No commit or publication is included.
