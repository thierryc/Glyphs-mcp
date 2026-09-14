## Lean v2 seven-tool workflow

Use this workflow with the seven-tool Glyphs 4 catalog. Prepare `start_job(kind="spacing")` on a
saved, clean disposable or user-authorized font. Use `glyphs` and `options.masters`
for scope; choose `options.reference` or per-glyph `options.references` explicitly
when the design calls for them. Otherwise the external spacing workflow records
its class-aware reference choice and any fallback. `options.widthMode` controls
automatic equal-figure detection or explicit width preservation. Tabular widths,
zero-width marks, retained metrics keys and native alignment are preserved.
This includes mixed assemblies with an effectively aligned component even
when the whole layer reports that it is not aligned. The native effective state
is checked after alignment evaluation; configured mode alone does not exclude
a mixed outline. Hosts without that API use the configuration conservatively.
Component placement continues to follow native alignment without overrides.

Differences at or below 0.001 font units are insignificant in preparation.
A negligible translation is skipped independently of a meaningful width change.
Restoration, native history and topology checks remain exact.

Translations write foreground node, anchor, and component positions explicitly.
Background images, guides, and component linear transforms remain unchanged
through apply, native history, and discard. A native position setter that cannot
retain a requested fraction makes that target unavailable during preparation;
review the reported exclusions without rounding the requested change.

Review `get_job.report`, including unavailable targets and the full external
report artifact, before applying. Use `apply_job` and verify the affected widths
and geometry through bounded `read_entities`; `outlineHash` verifies translated
geometry without returning every node. Native displayed bearings can be rounded;
physical fractional bearings must be checked from output coordinates or detached
native measurements. Use `discard_job` for whole-job restoration. Save remains
the user's acceptance action. The job offers sampled suggestions and better
reference selection, not universally optimal optical spacing. Do not introduce
Tunni, compensated scaling, smoothness repair or a balanced italic engine here.
