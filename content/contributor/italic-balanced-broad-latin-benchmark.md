# Broad-Latin Balanced italicification benchmark

## Purpose

This clean-room benchmark evaluates the experimental Glyphs MCP italic
first-pass workflow across 543 encoded glyphs in two open-source sans-serif
families. It compares Raw, Cursivy, and Balanced candidates generated from the
same Roman outlines.

The generated outlines are design-assistance evidence, not finished italics.
The official Inter and Noto Sans italics are qualitative references containing
deliberate drawing, spacing, component, and character-form decisions that a
mechanical first pass should not attempt to reproduce automatically.

## Fixed coverage

The committed
[manifest](../../scripts/data/italic_broad_latin_manifest.json) fixes the
Unicode value and source glyph name for every row:

| Group | Glyphs |
| --- | ---: |
| Basic Latin | 95 |
| Latin-1 | 91 |
| Latin Extended through `U+024F` | 259 |
| General Punctuation | 48 |
| Currency Symbols | 23 |
| Letterlike Symbols | 10 |
| Number Forms through `U+218F` | 17 |
| **Total per family** | **543** |

Two historical source-name differences are mapped by Unicode rather than by
name: Inter `Tcommaaccent` maps to Noto Sans `Tcedilla` at `U+0162`, and Inter
Latin `Iota` maps to Noto Sans `Iota-latin` at `U+0196`.

## Promotion result

Balanced passed every safety and quality gate and is the selected experimental
mode:

| Family | Topology | Source unchanged | Compensated pairs | Raw error | Cursivy error | Balanced error | Anchor error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Inter v4.1 | 543/543 | 543/543 | 135 | 2.7812 | 1.8078 | <0.00000000000004 | 0 |
| Noto Sans | 543/543 | 543/543 | 102 | 1.2912 | 0.8393 | <0.00000000000002 | 0 |
| Equal-family mean | — | — | 237 | 2.0362 | 1.3235 | <0.00000000000003 | — |

There were no generation failures, partial results, unexpected explicit
component-master mismatches, or unsafe applied compensations. Thirteen
pathless glyphs per family were retained without topology changes. Balanced
reduced mean source-width error by more than 99.99% versus both alternatives
in each family, exceeding the required 50% margin.

The near-zero result is expected only for confidently accepted straight-side
pairs: full compensation explicitly restores their measured source
perpendicular width. It does not claim optical completion or general
equivalence to the official italic.

## Raster review

All 543 glyphs were rendered at 2× scale in nine contact and nine difference
pages per family, with no page containing more than 64 glyphs. The full
paginated evidence and per-glyph JSON remain in the ignored
`.cache/italic-benchmark/results-broad` directory.

The committed audit sheets deterministically combine compensated glyphs,
largest official-italic differences, every coverage group, and evenly spaced
manifest samples. Click an image for its full 144-DPI source.

### Inter v4.1

[![Inter Broad-Latin audit contact sheet](images/italic-balanced-inter-v4.1-broad-audit.png)](images/italic-balanced-inter-v4.1-broad-audit.png)

[![Inter Broad-Latin audit difference sheet](images/italic-balanced-inter-v4.1-broad-audit-diff.png)](images/italic-balanced-inter-v4.1-broad-audit-diff.png)

### Noto Sans

[![Noto Sans Broad-Latin audit contact sheet](images/italic-balanced-noto-sans-cb097900-broad-audit.png)](images/italic-balanced-noto-sans-cb097900-broad-audit.png)

[![Noto Sans Broad-Latin audit difference sheet](images/italic-balanced-noto-sans-cb097900-broad-audit-diff.png)](images/italic-balanced-noto-sans-cb097900-broad-audit-diff.png)

Dark pixels overlap, blue pixels occur only in Balanced, and coral pixels occur
only in the comparison outline. Thin blue and coral lines show the respective
advance widths.

| Family | Balanced vs Raw | Balanced vs Cursivy | Balanced vs official |
| --- | ---: | ---: | ---: |
| Inter v4.1 | 0.269% | 0.151% | 7.237% |
| Noto Sans | 0.205% | 0.088% | 29.219% |

These are descriptive mean silhouette differences, not acceptance thresholds.
The largest official-italic differences also reveal intentional component and
drawing changes. Inter differs most in `quotereversed`,
`reversedsemicolon`, `questiondown`, `acute`, and `Oopen`; Noto Sans differs
most in `reversedsemicolon`, `questiondown`, `brokenbar`, `bar`, and `degree`.

## Reproduction

Keep the pinned source checkouts beneath the ignored
`.cache/italic-benchmark` directory, then run:

```sh
/usr/local/bin/python3.12 scripts/benchmark_italic_sans_broad.py \
  --render-scale 2 \
  --page-size 64 \
  --audit-limit 64
```

The script exits successfully only when the conditional promotion gate selects
Balanced. Its JSON records every topology result, source-mutation check,
anchor and component position, bounds and advance-width delta, detected and
skipped stem pair, width measurement, raster comparison, failure, and runtime.

Inter is pinned at
[`e3a3d4c57d5ecc01453a575621882a384c1995a3`](https://github.com/rsms/inter/tree/e3a3d4c57d5ecc01453a575621882a384c1995a3).
Noto Sans is pinned at
[`cb097900c74b26e6dcab899b4f07b2bc79dd80c4`](https://github.com/notofonts/latin-greek-cyrillic/tree/cb097900c74b26e6dcab899b4f07b2bc79dd80c4).
Both use the SIL Open Font License 1.1. No font source or binary is committed.

## Clean-room provenance

The benchmark exercises the repository's original interpolation and
straight-stem correction engine. It does not call, inspect, decompile, or copy
Italify or another proprietary implementation. The same conservative
detector, correction limits, and promotion rules apply to both families
without family-specific optical tuning.
