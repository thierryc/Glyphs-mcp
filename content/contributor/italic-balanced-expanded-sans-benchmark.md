# Expanded Balanced italicification benchmark

> This 66-glyph study is retained as historical evidence. The
> [543-glyph Broad-Latin promotion benchmark](italic-balanced-broad-latin-benchmark.md)
> is the current release gate and canonical result.

## Scope

This follow-up expands the clean-room benchmark from 26 Inter glyphs to 66
glyphs in each of two SIL Open Font License sans-serif families:

- All 26 uppercase Latin letters.
- All 26 lowercase Latin letters.
- All ten lining figures (`zero` through `nine`).
- `parenleft`, `ampersand`, `adieresis`, and `iacute` from the original set.

The compared columns remain Roman, Raw, Cursivy fallback, Balanced, and the
family's official Italic. Official italics are qualitative references, not
numeric pass/fail targets; both Inter and Noto Sans contain deliberate
redrawing beyond mechanical obliquing.

## Results

| Family | Angle | Topology | Accepted pairs | Raw error | Cursivy error | Balanced error | Anchor error |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Inter v4.1 | 9.4° | 66/66 | 15 | 2.0106 | 1.3069 | &lt;0.00000000000004 | 0 |
| Noto Sans | 12° | 66/66 | 12 | 2.0413 | 1.3268 | &lt;0.00000000000002 | 0 |

Balanced reduced mean source-width error by more than 99.99% versus both Raw
and Cursivy across accepted pairs in both families. This near-zero result is
expected for the conservative pairs: full compensation explicitly restores
the measured source perpendicular width. It does not imply that the generated
outlines reproduce the optical decisions in the official italics.

Accepted pairs by group:

| Family | Uppercase | Lowercase | Numerals | Extras |
| --- | ---: | ---: | ---: | ---: |
| Inter v4.1 | 9 | 5 | 1 | 0 |
| Noto Sans | 8 | 3 | 1 | 0 |

## Raster difference review

The high-resolution silhouette diff aligns every comparison to the same glyph
origin and baseline. Dark pixels overlap, blue pixels exist only in Balanced,
and coral pixels exist only in the reference. Thin blue and coral vertical
lines mark the respective advance widths.

Mean differing pixels as a share of the union silhouette:

| Family | Balanced vs Raw | Balanced vs Cursivy | Balanced vs official |
| --- | ---: | ---: | ---: |
| Inter v4.1 | 0.172% | 0.089% | 6.206% |
| Noto Sans | 0.318% | 0.156% | 27.472% |

These raster ratios are descriptive, not acceptance targets. Raw and Cursivy
differ from Balanced only where the conservative correction engine acts.
Official-italic differences also include redrawing, sidebearing changes, and
other family-specific optical decisions. The largest Inter differences occur
in `q`, `d`, `a`, `adieresis`, and `f`; Noto Sans is most different in `w`,
`v`, `Y`, `W`, and `M`.

### Inter v4.1

![Expanded Inter Roman, generated modes, and official Italic](images/italic-balanced-inter-v4.1-expanded.png)

![Inter Balanced silhouette differences against Raw, Cursivy, and official Italic](images/italic-balanced-inter-v4.1-diff.png)

### Noto Sans

![Expanded Noto Sans Roman, generated modes, and official Italic](images/italic-balanced-noto-sans-cb097900-expanded.png)

![Noto Sans Balanced silhouette differences against Raw, Cursivy, and official Italic](images/italic-balanced-noto-sans-cb097900-diff.png)

The outline contact sheets are rendered at `4300 × 24540` pixels with 144 DPI
metadata. Difference sheets are `3340 × 24584` pixels at the same density.

## Sources and exact masters

Inter remains pinned at
[`e3a3d4c57d5ecc01453a575621882a384c1995a3`](https://github.com/rsms/inter/tree/e3a3d4c57d5ecc01453a575621882a384c1995a3):

- Roman `Regular`: `C698F293-3EC0-4A5A-A3A0-0FDB1F5CF265`,
  `opsz=14`, `wght=400`.
- Italic: `11F4534A-B963-4AB5-820F-DAF9A20CD933`,
  `opsz=14`, `wght=400`, `italicAngle=9.4`.

Noto Sans is available from
[Google Fonts](https://github.com/google/fonts/tree/main/ofl/notosans) and is
pinned to the upstream
[`cb097900c74b26e6dcab899b4f07b2bc79dd80c4`](https://github.com/notofonts/latin-greek-cyrillic/tree/cb097900c74b26e6dcab899b4f07b2bc79dd80c4)
source:

- Roman `Regular`: `9FF96064-8718-4A86-A5C8-73C592101F67`.
- Italic: `9733853B-DD8E-49B4-939D-1F0D465E8B6E`,
  `italicAngle=12`.
- Both use exact source coordinates `wght=90`, `wdth=100`, corresponding to
  the regular external instance at `wght=400`, `wdth=100`.

Both families use the SIL Open Font License 1.1:
[Inter license](https://github.com/rsms/inter/blob/e3a3d4c57d5ecc01453a575621882a384c1995a3/LICENSE.txt)
and
[Noto Sans license](https://github.com/notofonts/latin-greek-cyrillic/blob/cb097900c74b26e6dcab899b4f07b2bc79dd80c4/OFL.txt).
No font source or binary is committed to this repository.

## Reproduction

Keep both source checkouts beneath the ignored `.cache/italic-benchmark`
directory. The Inter checkout is described in the original report. Fetch the
pinned Noto Sans source with:

```sh
git clone --filter=blob:none --no-checkout \
  https://github.com/notofonts/latin-greek-cyrillic.git \
  .cache/italic-benchmark/noto-sans-cb097900c74b26e6dcab899b4f07b2bc79dd80c4
git -C .cache/italic-benchmark/noto-sans-cb097900c74b26e6dcab899b4f07b2bc79dd80c4 \
  checkout --detach cb097900c74b26e6dcab899b4f07b2bc79dd80c4
```

Then run:

```sh
/usr/local/bin/python3.12 scripts/benchmark_italic_sans_expanded.py
```

The default `--render-scale 2` produces the committed 144-DPI evidence.
Values from `1` to `4` are accepted when a larger local inspection image is
needed.

The script fails clearly when either exact Roman/Italic master pair is absent,
when any of the 66 glyphs is missing, when the official italic angle does not
match, or when a geometry acceptance check fails. Generated JSON and PNG files
are written beneath `.cache/italic-benchmark/results-expanded`. The JSON
includes per-glyph and aggregate silhouette-difference ratios.

## Clean-room provenance

This benchmark exercises the repository's original interpolation and
straight-stem correction engine. It does not call, inspect, decompile, or copy
Italify or any other proprietary implementation. The same conservative
acceptance rules are used for both families, without family-specific detector
thresholds or attempts to reproduce their designed italic forms.
