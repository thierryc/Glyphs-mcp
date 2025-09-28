### Advanced TrueType Hinting

Use the following custom parameters to further configure the TT hinting of the exported font files.

###### TTFOvershootSuppressionBelowPPM

Add this parameter in “File” → “Font Info…” → “Font” (Cmd-I).
Set it to the pixel size, below which overshoots are collapsed to the flat edge of their zone.
The flat edge is the position of a zone as configured in the TTFZones parameter.

###### TTZoneRoundingThreshold

Add this parameter in either the “Font” or “Exports” tab in the Font Info window (Cmd-I).
The “Font” value is used for all instances where the parameter is not set.
This value controls the likelihood of a positive zone being pushed up a pixel.
It takes a small decimal number, typically something around 0.1 or 0.2.
The value is added to any positive zone position before rounding, and added twice to the x-height zone (the one named “xHeight” in the TrueType zones).
Its default value is 0.09375.

For example: At a certain font size, the small caps zone ends up at 6.45 px, and the x-height at 5.25 px.
Without any change, the small caps zone rounds and snaps to a height of 6 pixels, while the x-height ends up with 5 pixels.
But when setting the rounding threshold to 0.2, the small caps height ends up at 6.45 + 0.2 = 6.65 ≈ 7 pixels, and the x-height at 5.25 + 2 × 0.2 = 5.65 ≈ 6 pixels.

###### TTMinimumDistance

Add this parameter in “File” → “Font Info…” → “Exports” (Cmd-I).
The default value is 0.25, meaning that any hinted stem will be drawn with a minimum length of a quarter pixel, regardless of which PPM size if it has a stem hint applied.
If the default value does not fit the design, add this parameter with a custom minimum distance (in pixels).

###### Control Value Program

See the TrueType Reference Manual for details.

Three custom parameters are added to the masters when opening a hinted TrueType font: CVT Table, prep Table Assembly, and fpgm Table Assembly.
These parameters contain the assembly code for the existing TT hinting and are rarely edited manually.
Instead, they are used not to lose the existing hinting instructions on export.
They correspond to the `cvt`, `prep`, and `fpgm` tables in the font.

###### gasp Table

Add this parameter in either the “Font” or “Exports” tab in the Font Info window (Cmd-I).
The “Font” value is used for all instances where the parameter is not set.
This parameter configures the grid-fitting and scan-conversion procedure for TrueType fonts.
It controls the two PPM thresholds at which the recommended on-screen rendering behavior changes.
The `gasp` table contains rendering recommendations for both a traditional Grayscale and a ClearType subpixel renderer.
However, keep in mind that a renderer may ignore the data stored therein.
The default threshold sizes are 8 and 20 PPM.
Because there are two thresholds, three ranges can be differentiated:

- Source for quoted parts: _Now read this: The Microsoft ClearType Font Collection_, Microsoft 2004, p. 14.“No Hinting & Symmetric”: Until the first threshold size, no grid-fitting is applied, and text is rendered with antialiasing wherever possible.“At very small sizes, the best appearance on grayscale devices can usually be achieved by rendering the glyphs in grayscale without using hints.”

- “Hinting & Asymmetric”: Between the two threshold sizes, the renderer is recommended to apply grid-fitting and suppress grayscale.“At intermediate sizes, hinting and monochrome rendering will usually produce the best appearance.”In ClearType, the matter is handled asymmetrically: vertical grid-fitting is applied, while horizontally, subpixel rendering is used.

- “Hinting & Symmetric”: Beyond the thresholds, the rasterizer is instructed to apply grid-fitting and render the shapes in grayscale.“At large sizes, the combination of hinting and grayscale rendering will typically produce the best appearance.”The ClearType rasterizer is instructed to apply symmetric smoothing. This uses antialiasing in the _{Y} direction in addition to horizontal subpixel rendering.“At display sizes on screen, […] this new improvement of the Windows font renderer produces smoother and cleaner-looking type.”