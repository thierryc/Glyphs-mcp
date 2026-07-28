# Three-family Broad-Latin deterministic italicification benchmark

## Purpose

This clean-room benchmark evaluates the experimental Glyphs MCP italic
first-pass workflow in Inter, Noto Sans, and IBM Plex Sans. It compares three
deterministic candidates generated from the same Roman outlines:

- **Raw** is a pure shear.
- **Partial compensation** is the legacy `cursivy` result key in this
  headless benchmark. It applies the repository's pure-Python stem correction
  at strength `0.35`; it does **not** invoke the Glyphs Cursivy filter.
- **Balanced** uses curve interpolation strength `0.75` followed by the same
  deterministic correction engine at full strength.

The generated outlines are design-assistance evidence, not finished italics.
The official italics are qualitative references containing deliberate
drawing, rhythm, spacing, component, and character-form decisions that a
mechanical first pass should not attempt to reproduce automatically.

## Fixed coverage

The committed
[manifest](../../scripts/data/italic_broad_latin_manifest.json) fixes 543
Unicode values and the Inter/Noto Sans source glyph names. IBM Plex Sans is
resolved by Unicode from its pinned Regular and Italic UFOs; 391 of the 543
values are present in both. The JSON evidence records all 152 unavailable Plex
entries rather than silently dropping them.

| Group | Fixed manifest | Inter | Noto Sans | IBM Plex Sans |
| --- | ---: | ---: | ---: | ---: |
| Basic Latin | 95 | 95 | 95 | 95 |
| Latin-1 | 91 | 91 | 91 | 91 |
| Latin Extended through `U+024F` | 259 | 259 | 259 | 158 |
| General Punctuation | 48 | 48 | 48 | 16 |
| Currency Symbols | 23 | 23 | 23 | 14 |
| Letterlike Symbols | 10 | 10 | 10 | 3 |
| Number Forms through `U+218F` | 17 | 17 | 17 | 14 |
| **Benchmarked total** | **543** | **543** | **543** | **391** |

Two historical Inter/Noto Sans source-name differences are mapped by Unicode:
`Tcommaaccent`/`Tcedilla` at `U+0162` and `Iota`/`Iota-latin` at `U+0196`.

## Result: geometry winner, promotion blocked

Balanced is the deterministic geometry winner in every family. It restores
the measured source width of accepted conservative stem pairs and has the
lowest equal-family mean error.

| Family | Topology | Source unchanged | Compensated pairs | Raw error | Partial error | Balanced error | Anchor error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Inter v4.1 | 543/543 | 543/543 | 135 | 2.7812 | 1.8078 | &lt;0.00000000000004 | 0 |
| Noto Sans | 543/543 | 543/543 | 102 | 1.2912 | 0.8393 | &lt;0.00000000000002 | 0 |
| IBM Plex Sans | 391/391 | 391/391 | 102 | 1.2607 | 0.8194 | &lt;0.00000000000002 | 0 |
| Equal-family mean | — | — | 339 | 1.7777 | 1.1555 | &lt;0.00000000000002 | — |

Balanced reduced mean source-width error by more than 99.99% versus both
alternatives in each family. This near-zero result applies only to confidently
accepted straight-side pairs. It does not measure optical completion or
similarity to a deliberately drawn italic.

The global promotion gate is nevertheless **blocked**. The review found
component transforms for which slanting a component locally and then applying
its component matrix (`L × S`) differs from shearing the complete Roman
construction (`S × L`):

| Family | Affected glyphs | Reflected cases | Other non-commuting cases | Safety gate |
| --- | ---: | ---: | ---: | --- |
| Inter v4.1 | 23 | 17 | 6 vertically scaled marks | Fail |
| Noto Sans | 2 | 2 | 0 | Fail |
| IBM Plex Sans | 0 | 0 | 0 | Pass |

This explains the earlier `d`/`q` observation. Inter constructs `d` from a
horizontally reflected `b` and `q` from a reflected `p`; local slant followed
by reflection reverses their apparent direction. IBM Plex Sans draws `d`,
`p`, and `q` directly, so those glyphs lean in the expected direction. The
problem is construction-dependent, not a negative angle being supplied to
selected glyphs.

The affected Inter rows are `d`, `q`, `dcaron`, `dcroat`,
`Ohungarumlaut`, `ohungarumlaut`, `Uhungarumlaut`, `uhungarumlaut`,
`dtopbar`, `Tonetwo`, `dzcaron`, `Udieresismacron`,
`udieresismacron`, `Adieresismacron`, `adieresismacron`, `Adotmacron`,
`adotmacron`, `dz`, `dcurl`, `quotereversed`, `paragraphreversed`,
`reversedsemicolon`, and `dong`. Noto Sans is affected at
`paragraphreversed` and `reversedsemicolon`.

No mode is recommended for global promotion until component transform order is
corrected and the three-family gate is rerun. This component issue is shared by
Raw, partial compensation, and Balanced; it does not change Balanced's
path-only geometry ranking.

## Raster review and mode separation

The 543 Inter glyphs, 543 Noto Sans glyphs, and 391 Plex glyphs were rendered
at 2× scale in pages of at most 64 glyphs. The full paginated evidence and
per-glyph JSON remain in the ignored
`.cache/italic-benchmark/results-broad-plex-review` directory.

The committed 144-DPI audit sheets prioritize component-direction risks,
accepted-pair glyphs, representative categories, and the largest qualitative
official-italic differences. Click an image for the full
`4300 × 23800` contact sheet or `4380 × 23844` difference sheet.

### Inter v4.1

[![Inter Broad-Latin audit contact sheet](images/italic-balanced-inter-v4.1-broad-audit.png)](images/italic-balanced-inter-v4.1-broad-audit.png)

[![Inter Broad-Latin audit difference sheet](images/italic-balanced-inter-v4.1-broad-audit-diff.png)](images/italic-balanced-inter-v4.1-broad-audit-diff.png)

### Noto Sans

[![Noto Sans Broad-Latin audit contact sheet](images/italic-balanced-noto-sans-cb097900-broad-audit.png)](images/italic-balanced-noto-sans-cb097900-broad-audit.png)

[![Noto Sans Broad-Latin audit difference sheet](images/italic-balanced-noto-sans-cb097900-broad-audit-diff.png)](images/italic-balanced-noto-sans-cb097900-broad-audit-diff.png)

### IBM Plex Sans

[![IBM Plex Sans Broad-Latin audit contact sheet](images/italic-balanced-ibm-plex-sans-71d012bc-broad-audit.png)](images/italic-balanced-ibm-plex-sans-71d012bc-broad-audit.png)

[![IBM Plex Sans Broad-Latin audit difference sheet](images/italic-balanced-ibm-plex-sans-71d012bc-broad-audit-diff.png)](images/italic-balanced-ibm-plex-sans-71d012bc-broad-audit-diff.png)

Dark pixels overlap, blue pixels occur only in the candidate, and coral pixels
occur only in the reference. Thin blue and coral lines show the respective
advance widths.

| Family | Partial vs Raw | Balanced vs Raw | Balanced vs Partial | Balanced vs official |
| --- | ---: | ---: | ---: | ---: |
| Inter v4.1 | 0.123% (64/543) | 0.269% (86/543) | 0.151% (59/543) | 7.237% |
| Noto Sans | 0.121% (46/543) | 0.205% (51/543) | 0.088% (40/543) | 29.219% |
| IBM Plex Sans | 0.106% (27/391) | 0.213% (50/391) | 0.114% (36/391) | 19.798% |

Values are mean silhouette differences; parentheses give the count of glyphs
with at least one different raster pixel. The median generated-mode difference
is zero in all families because the conservative correction engine changes
only accepted stem pairs. This is why Raw, partial compensation, and Balanced
look identical for most glyphs, including many curved forms.

Official-italic differences remain qualitative and are not an optimization
target. They show where a designer deliberately redrew forms beyond a
mechanical emphasis companion.

## Reproduction

Keep the pinned source checkouts beneath the ignored
`.cache/italic-benchmark` directory, then run:

```sh
python3.12 scripts/benchmark_italic_sans_broad.py \
  --render-scale 2 \
  --page-size 64 \
  --audit-limit 64
```

The script currently exits non-zero because the component-transform safety gate
blocks promotion. Its JSON records coverage, topology, source immutability,
anchors, components and transform risks, bounds, advance widths, detected and
skipped stem pairs, width measurements, all four raster comparisons, failures,
and runtime.

Sources are pinned at:

- [Inter `e3a3d4c57d5ecc01453a575621882a384c1995a3`](https://github.com/rsms/inter/tree/e3a3d4c57d5ecc01453a575621882a384c1995a3)
- [Noto Sans `cb097900c74b26e6dcab899b4f07b2bc79dd80c4`](https://github.com/notofonts/latin-greek-cyrillic/tree/cb097900c74b26e6dcab899b4f07b2bc79dd80c4)
- [IBM Plex Sans source mirror `71d012bccb31a2e282cc46de63b387ff7f676287`](https://github.com/googlefonts/plex/tree/71d012bccb31a2e282cc46de63b387ff7f676287/IBM-Plex-Sans)

IBM Plex's [upstream project](https://github.com/IBM/plex) and all three pinned
benchmark sources use the SIL Open Font License 1.1. No font source or binary
is committed.

## Clean-room provenance

The benchmark exercises the repository's original interpolation and
straight-stem correction engine. It does not call, inspect, decompile, or copy
Italify or another proprietary implementation. The same conservative detector,
correction limits, and promotion rules apply without family-specific optical
tuning.
