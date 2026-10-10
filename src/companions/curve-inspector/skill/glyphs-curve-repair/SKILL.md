---
name: glyphs-curve-repair
description: Inspect and repair curve/curve and line/curve joins in Glyphs 4 using Curve Inspector's shared native super-smooth engine, or explicit SuperTool handle repair for curve/curve joins.
metadata:
  surface: glyphs-mcp-v2
---

# Curve Inspector · Inspect & Repair

Use the installed Curve Inspector engine, never recreate its formulas in a
script. This skill package ships with the companion; managed-catalog registration
is deferred until a release can pin its actual source commit.

Resolve the intended document, glyph, owning layer and foreground/background
surface. Select shared on-curve nodes only: both adjoining segments are included
automatically. Bind joins once as zero-based `(path, node)` pairs. Repair
analysis is independent of the Reporter's 128-cubic display cap.

Default to `native-star` and `maxDeviationEm=0.001`. Stars preserve stored
coordinates while changing the effective outline. The same native method uses
stars between curves and raindrops between lines and curves, in either direction.
`supertool-handles` supports curve/curve joins only and is the
explicit fixed-on-curve alternative; `tunniBalance` defaults to false and its
result must still pass G2 and neighbor checks. Preserve corners and locks.

Use [run_repair.py](scripts/run_repair.py) through the existing advertised
`python_script` workflow. The helper imports the installed shared engine and
checks its version; a missing companion is an installation gap, not permission
to copy an algorithm into the script. Choose `operation=analyze` or `propose`
for preview-only requests. `operation=repair` recomputes and applies a guarded
proposal under existing repair authorization, then verifies actual native output.
Carry `expectedFingerprint` from a reviewed proposal into application.

Provide `joins`, `allJoins`, `allLayers`, `method`, `maxDeviationEm`,
`tunniBalance` and optional `region` as needed. `region` is an explicit list of
`[minimum,maximum]` pairs in the font's native axis order. Report the declared
region, families, expected/evaluated locations, maximum continuous outline
bound, its reported metric, and effective join movement. Fixed-correspondence
cubics retain the exact squared-difference integral; native expanded chains
report that integral as null. Report generated-segment G1 separately from G2 at
the requested source join and from drawing-grid quantization. The 4096-location
limit never truncates. A blocked mixed selection must be explained, not silently
reduced to an eligible subset.

Use [native and recovery notes](references/native-and-recovery.md) when executing
or explaining a refusal. Use the existing qualified `dekink-native` workflow
for HOI-specific trajectory problems; it is distinct from this G2 operation.
Do not claim general conditional-family or export qualification from ordinary
master tests. An unsupported family must remain a visible refusal.

V2 owns document identity and script jobs. Respect its saved-baseline rules.
Native script restoration reloads the whole saved font and discards later
unsaved changes; it is not selective patch rollback. Preview-only authorization
does not authorize live edits, Save, installation or restart. Existing repair
authorization need not be requested again for the same guarded scope.
