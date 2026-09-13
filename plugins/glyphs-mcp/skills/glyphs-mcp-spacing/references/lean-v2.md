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
a mixed outline. Verify the current private installation's advertised workflow;
missing capabilities require a coordinated installation update.
Component placement continues to follow native alignment without overrides.

## Request and options

Reuse the known connection and document ID. A dirty or unsaved font can still be
read with `read_entities`; only job preparation needs a clean saved source.
Do not save a user's font just to satisfy that prerequisite. Scope real-font
work to explicit glyphs and verified native master IDs; omitted masters means
all masters, including masters outside the current Edit View. Omit `delta`.

For `start_job`, replace both labelled placeholders with discovered live IDs:

```json
{
  "document_id": "<retained document ID>",
  "kind": "spacing",
  "glyphs": ["H", "n", "o"],
  "options": {
    "masters": ["<verified native master ID>"],
    "reference": "auto",
    "widthMode": "preserve",
    "area": 400,
    "depth": 15,
    "sampleStep": 5
  }
}
```

| Option | Default | Accepted values and meaning |
|---|---|---|
| `reference` | `"auto"` | Nonempty string, at most 255 characters. `auto` chooses by glyph class; `*` uses the target glyph; another name selects that reference. |
| `references` | `{}` | Per-glyph overrides, for example `{"V":"H","n":"x"}`; at most 10,000 entries with nonempty glyph names and reference strings. |
| `masters` | `[]` | List of at most 100 exact native master IDs; empty or omitted selects all masters. |
| `widthMode` | `"auto"` | `auto`, `preserve`, or `proportional`. `preserve` retains advances. `proportional` disables equal-default-figure detection but does not override tabular-name or fixed-pitch protection. |
| `area` | `400` | Finite number in 0–10,000 inclusive, scaled by UPM and x-height; this is not a direct sidebearing distance. |
| `depth` | `15` | Finite number in 0–100 inclusive, expressed as a percentage of x-height. |
| `sampleStep` | `5` | Finite number in 0.5–100 inclusive, in font units; at most 4,096 intervals per measurement. Finer sampling costs more work. |

Unknown options and booleans in numeric options are rejected. An unavailable
explicit reference is reported as unavailable; inspect it rather than silently
substituting another reference. Review the selected reference and any automatic
fallback in the full report. Keep negative bearings when the geometry warrants
them; do not clamp the proposal to zero. An authored font's current spacing may
already be intentional: review a small scope before expanding it.

Differences at or below 0.001 font units are insignificant in preparation.
A negligible translation is skipped independently of a meaningful width change.
Restoration of captured data and topology checks remains exact. The known native
Undo dirty-state issue is separate: restored data may still leave the font
marked edited. Do not force it clean, auto-save, or claim clean-state restoration.

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
native measurements. Exact patch application does not establish continuous
measurement accuracy or optical quality. Sampling can miss details between
heights; use the reported measurement range/count and a native proof before
acceptance. Finer sampling alone is not proof of correct optical spacing.
Use native Edit View Undo/Redo for the relevant glyph and `discard_job` for
whole-job restoration. Save remains
the user's acceptance action. The job offers sampled suggestions and better
reference selection, not universally optimal optical spacing. Do not introduce
Tunni, compensated scaling, smoothness repair or a balanced italic engine here.
