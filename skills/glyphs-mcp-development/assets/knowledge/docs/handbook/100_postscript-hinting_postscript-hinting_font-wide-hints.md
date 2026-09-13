### Font-Wide Hints

Before adding glyph-level hinting, define a set of parameters that apply to all hinting throughout the font.
These font-level hints are stored in the so-called _PostScript Private Dictionary_ inside the exported font.
For an in-depth discussion, see

- the Adobe Type 1 Font Format specification specifically pages 35–45;

- Robothon 2012: Postscript hints approximately 35 min, a video presentation about PostScript hinting by Miguel Sousa from Adobe.

#### Standard Stems

Stem widths are the thicknesses of letter strokes.
A _vertical_ stem is the width of a vertical stroke of a letter, for example, the thickness of the I, or the thicknesses of left and right curves of an O.
A _horizontal_ stem is the thickness of a horizontal stroke movement, for example, the serifs or crossbars of A and H, or t and f, or the upper and lower curves of an O.

_Standard_ stems are average values, as representative as possible, for as many stem widths in the font as possible.
The autohinter needs good standard stem values to recognize the stems and insert glyph-level hints automatically.
And the screen rasterizer can make use of these values to optimize the pixel rendering, especially synchronizing stem thicknesses across the whole font at low resolutions.

Try to find as few as possible and as representative as possible values for horizontal and vertical stem widths and enter them in the “Masters” tab of Font Info (“File” → “Font Info…” → “Masters”, Cmd-I).
See Stems for details on editing stem values in Font Info.

If two values are close to each other, consider merging them into one average value.
Quickly measure the thickness of stems by selecting two nodes and looking at the Info box (Cmd-Shift-I) or by switching to the Measurement tool.
See Measuring.

For instance, if the measured values are 68, 71, 72, 74, 75, 82, 83, and 85 for the vertical stems, pick 75 or 80 for the standard vertical stem because either would be a good median value for most of the stem measures.

PPM stands for pixel per em and is a measurement for pixel density.

By using a single stem value, the stems will scale more uniformly across low PPMs.

Theoretically, up to twelve stem width values can be considered for each orientation.
But the best practice of trying to find as few as possible will typically either result in a single representative value for all stems or in two values: one for lowercase and one for uppercase letters, or (in the case of horizontal stems) one for an average horizontal stroke, and one for the serifs.
Use a second or third value only if it is acceptable that the associated stems will have different thicknesses at the same pixel size.
For instance, for a vertical standard stem set at 70 units and another at 80 units, the first stem may be displayed two pixels wide, while the other stem may get three pixels at the same pixel size.

The first horizontal and vertical stem values are the most important ones.
Use a value that represents the most-used glyphs, typically the lowercase letters.
Other functions in Glyphs also use these values, such as the Cursivy algorithm or the “Rounded Font” filter.
Any stem values that follow are exclusively used for hinting.
The horizontal stems also play a role in TrueType hinting.

When interpolating between masters, stems with the same name in both masters are used to interpolate the in-between stem value.

#### Alignment Zones

When a font is rendered with very few pixels on a computer screen, all the x-heights should use the same amount of pixels vertically.
The same applies to ascenders of letters like f, h, or k, and to descenders of g, p or y, and to the heights of all capital letters.
For many designs, all letters should share the same baseline when rasterized at a low resolution.

But all these letters usually do not align precisely.
For instance, the bottom of a lowercase o will extend slightly below the baseline, while the serifs of an n may sit precisely on it.
Or the apex of an uppercase A may extend a little bit beyond the height of an uppercase H.
This difference, usually some ten to fifteen units, is commonly referred to as _overshoot_.

Alignment zones are a way to tell the rasterizer about the overshoots.
Overshoots cannot help to provide an optically balanced text at small pixel sizes, so their display should be suppressed.
More precisely, at low resolutions, any path constellation with a horizontal stem or ghost hint attached to it that reaches into an alignment zone will be vertically aligned to the base of the zone.

Alignment zones take two values: a position and a size.
The position is the vertical height of the zone, usually the vertical metrics, like x-height or ascender.
The position is sometimes also referred to as the _flat edge_ of a zone.
The size is the thickness of the maximum overshoot that may appear at that position.
If the overshoot extends above the position (x-height, small caps height, cap height, ascender), the size value must be positive.
Such zones are referred to as _top zones_.
If, however, the overshoots extend below the position (typically for the baseline or descender), the size must be negative and is referred to as a _bottom zones_.
See Metrics & Alignment Zones for details on editing the alignment zones of a font master.

A typical alignment zone setup: top zones with positive sizes at ascender, cap height and x-height; bottom zones with negative sizes at baseline and descender.

Alignment zones should be as small as possible, so do not try to make them larger “to be on the safe side”.
More precisely, the maximum size of an alignment zone is constrained by the _{blueScale} value (see below), which implies that no zone must be larger than 240 ÷ (240 × _{blueScale} − 0.98).
In any event, a zone must not be larger than 25 units.
There may be a maximum of 6 top zones, 5 bottom zones, and the baseline zone.
Zones must not overlap.
There must be a minimum distance of one unit between them; the larger, the better.
The baseline zone must have a position value of zero.

If the font uses an alternative grid (see
Grid Spacing & Subdivision), extend the scope of the zones by one unit in both directions to catch potential small rounding errors for vertical node positions.
That is, the position must be shifted by one unit and the size by two units.
Only the baseline zone must be kept at position zero while its size is increased by one unit.

#### Custom Parameters

Apart from the alignment zones and standard stems, there are more optional parameters in the Private Dictionary: blueFuzz, blueScale, blueShift, and Family Alignment Zones.
In Glyphs, set these values as custom parameters.
See the description in Glyphs when adding the custom parameters for more details.