# Hinting guide and primary sources

Research checked 2026-10-27. This is a decision guide, not a copied manual.
Specifications define encoding; vendor documentation describes an exporter;
matched rendering establishes behavior in a particular engine/version. Prefer
current primary documentation over an old forum workaround. Recheck changing
exporter support when the installed version differs.

## Technology and scope

CFF/CFF2 describe stems/edges and alignment regions to a rasterizer; TrueType
instructions control point movement through programs. CFF2 supports variation
of outlines and hint data. Web containers do not determine outline flavor.
[Microsoft comparison of outline formats](https://learn.microsoft.com/en-us/typography/opentype/spec/glyphformatcomparison).

Shape fidelity and tiny-size regularity can conflict. Irregular handwriting,
connected scripts and icons may legitimately benefit from fewer or no hints.
Make the decision for the intended use, not from the font's category alone.
[Glyphs handbook: PostScript hinting](https://handbook.glyphsapp.com/postscript-hinting/).

## PostScript font-wide settings

Measure representative straight strokes and round bowls, grouped by intended
visual weight. Keep a small representative set; the first stem has particular
importance, often the lowercase. Keep compatible stem/zone definitions across
masters. A measurement from one “I” is evidence, not an approved family-wide
calibration. [Glyphs font-wide hints](https://handbook.glyphsapp.com/postscript-hinting/font-wide-hints/).

Zones should capture intended flat/overshoot extrema, not neighboring unrelated
features. Review baseline, x-height, caps, ascenders, descenders and any deliberate
extra height groups. BlueScale governs overshoot suppression; BlueShift extends
suppression for small overshoots; BlueFuzz affects zone capture. Family zones
are a separate cross-style alignment choice. Change one control at a time.
For Glyphs' 1000-unit planning recipe:

```
blueScale = (first_ppem_with_overshoot * 72 / 300 - 0.49) / 240
max_planned_ppem = (0.49 + 240 / largest_zone_units) / 72 * 300
```

The recipe's planned integer transition is not a universal measured rasterizer
threshold. Check UPM/FontMatrix and the target engine before translating units.
A scale-times-zone concern is diagnostic, never an automatic replacement with
0.039625. [Glyphs autohinting and parameter guidance](https://glyphsapp.com/learn/hinting-postscript-autohinting).

## PostScript glyph hints

Manual PS and auto can coexist in a font, but do not complement one another
within a single glyph in Glyphs. A manually hinted glyph needs a complete manual
strategy. Horizontal hints capture horizontal features and zone alignment;
vertical hints describe vertical features. Ghost hints align a lone top/bottom
edge without inventing a thick stroke. Prefer linked nodes when suitable and
check compatible master correspondence and `Get Hints From Master` behavior.
[Glyphs manual PS tutorial](https://glyphsapp.com/learn/hinting-manual-postscript-hinting),
[handbook manual hinting](https://handbook.glyphsapp.com/postscript-hinting/manual-hinting/).

CFF Type 2 stores stem and mask operations, possibly in subroutines. A single
operator can declare multiple stems; an omitted vertical operator can be implied
before a mask. Masks select active non-overlapping hints. Edge widths -20/-21
are special encodings, not negative physical stroke measurements. Flex operators
encode shallow paired curves. Do not remove masks or count string tokens as if
they were all independent physical stems.
[Adobe Type 2 specification, technical note 5177](https://adobe-type-tools.github.io/font-tech-notes/pdfs/5177.Type2.pdf).

Glyphs generates flex behavior at export when the curve/zone conditions qualify;
it is not a generic manual “flex hint” to insert in every contour. This can make
an exporter change look like a hint-count change without a source hint record.
[Glyphs handbook autohinting/flex](https://handbook.glyphsapp.com/postscript-hinting/autohinting/).

## TrueType and variable caveats

In Glyphs, manual TT and ttfautohint use different global programs. Select the
pipeline for an export rather than assuming per-glyph mixing. Its Snap/Stem/
Shift/Interpolate instructions establish relations; deltas are final, sparse
pixel corrections. Glyphs' current tutorial says its delta hints and hints to
synthetic overlap-intersection nodes are ignored in variable export. This is an
exporter-specific limitation, not a claim that the TT format cannot vary hints.
Use compatible existing outline points and inspect actual output.
[Glyphs manual TT tutorial](https://glyphsapp.com/learn/hinting-manual-truetype-hinting).

The TT autohint tutorial currently scopes its route to static exports and warns
about variable export. Verify installed support before promising a variable
workflow. Test the intended Windows application/browser, not only macOS.
[Glyphs TrueType autohinting](https://glyphsapp.com/learn/hinting-truetype-autohinting).

The ttfautohint library removes existing bytecode and replaces it with generated
instructions. Its component handling, script coverage and options matter; use
the actual version's documentation, preserve the original, and never assume an
in-place call is an incremental hint repair.
[Werner Lemberg's ttfautohint manual](https://freetype.org/ttfautohint/doc/ttfautohint.html).

TT programs use shared control values and point relations, so moving a source
point, changing topology or adding outline cleanup can invalidate assumptions.
Inspect `cvt `, `fpgm`, `prep`, per-glyph programs and, for variable data, `cvar`.
An imported assembly program is not safely editable as arbitrary PS stems.
[Microsoft TrueType instruction tutorial](https://learn.microsoft.com/en-us/typography/truetype/hinting-tutorial/hinting-and-truetype-instructions),
[Apple TrueType reference: instructing fonts](https://developer.apple.com/fonts/TrueType-Reference-Manual/RM03/Chap3.html).

`gasp` recommends grid fitting and grayscale behavior over ppem ranges; it does
not guarantee that every renderer follows that recommendation. Do not use a
`gasp` change to claim a fixed glyph defect without engine evidence.
[Microsoft gasp specification](https://learn.microsoft.com/en-us/typography/opentype/spec/gasp).

## CFF2 and modern external autohinting

CFF2 has private dictionaries, stem/edge hints and masks, and can blend some hint
operands. Check all dictionaries and axis locations. Hint association and mask
semantics must remain valid through variation; default-instance validity is
insufficient. BlueScale is not a blendable field. The helper's default-location
operator inventory does not certify these semantics.
[Current Microsoft CFF2 specification](https://learn.microsoft.com/en-us/typography/opentype/spec/cff2).

Adobe's old standalone psautohint repository is retired in favor of AFDKO
`otfautohint`. The latter documents direct variable CFF2 hinting. Re-hinting can
change programs substantially. Discover its installed options/version, use a
separate output, retain decimal precision where supported, and do not enable
outline-changing options for a hint-only experiment. Verify geometry and layout
before inspecting pixels; tool success alone is not acceptance.
[Adobe psautohint retirement notice](https://github.com/adobe-type-tools/psautohint),
[Adobe AFDKO otfautohint notes](https://github.com/adobe-type-tools/afdko/blob/develop/docs/otfautohint_Notes.md).

## Renderers and proof interpretation

FreeType exposes CFF hinting-engine and stem-darkening controls. Record driver,
load target, antialiasing and darkening settings; a library version alone does not
specify them all. Native CFF rendering can differ from the runtime auto-hinter.
[FreeType CFF driver](https://freetype.org/freetype2/docs/reference/ft2-cff_driver.html).

Gamma, compositing and stem darkening affect apparent stroke weight. Apparent
sharpness can come at the cost of darkness or lost counters. Compare baseline,
weight rhythm and text at actual size, then magnify the existing pixels without
smoothing. Keep pixel/device scale and phase explicit. Do not turn a historical
statement that “Mac ignores hints” into a guarantee of pixel identity: a
font-wide parameter can affect that renderer differently from glyph hints.
[FreeType rendering discussion by Nikolaus Waxweiler and Graham Asher](https://freetype.org/freetype2/docs/hinting/text-rendering-general.html).

OTS/table parsing tests structure; FontBakery tests selected engineering rules.
Neither decides optical quality. CoreText is useful evidence for Apple; Adobe,
DirectWrite and browser/app acceptance require those actual environments.
Label unavailable engines as untested, not passed or implicitly equivalent.

## Native API source

Use documented GSHint flags and links, not guessed numeric classifications.
`isCorner` includes cap/brush helpers; `stem` is a TT stem index and can contain a
native sentinel. A missing target can be a valid ghost rather than a broken link.
Current API examples are at the
[Glyphs SDK](https://github.com/schriftgestalt/GlyphsSDK/blob/c0352321d30a06006f18e94d600f5caf43d06f1b/ObjectWrapper/GlyphsApp/__init__.py).
Local offline documentation and actual runtime verification take precedence over
assuming an old Glyphs 2/3 UI recipe names a Glyphs 4 scripting method.

## Cross-editor checks

FontLab separately documents PS and TT setups and requires reviewing automatically
proposed stem/zone values. Its conversion facilities are application-specific;
do not transfer UI commands, units or export assumptions into Glyphs without
checking their meaning. [FontLab hinting a font](https://help.fontlab.com/fontlab/7/manual/Hinting-a-Font/).

FontForge explains active hint substitution and counter groups, and documents
auto-regeneration of stale hints and its own per-glyph auto-hint suppression
state. These differ from simply retaining a raw coordinate hint in a Glyphs
source. Preserve an import's original programs and test conversion behavior;
opening a font in another editor does not guarantee round-trip hint fidelity.
[FontForge technical hinting guide](https://fontforge.org/docs/techref/hinting.html).
