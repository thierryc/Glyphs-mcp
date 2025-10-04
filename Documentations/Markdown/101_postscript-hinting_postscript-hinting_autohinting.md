### Autohinting

If the font-wide parameters (alignment zones and standard stems) are correctly set, activate the autohinter by checking the “Autohint” option in the “File” → “Export” dialog.
Enforce this setting with the “Autohint” custom parameter.

Test the hinting in an Adobe application (see Previewing in Adobe Applications).
Write a test text and zoom out far enough to display the letters with a few pixels only.
Then zoom in using the operating system’s Zoom function (configurable in the Accessibility settings of the System Settings).
If necessary, tweak the font settings or manually hint a problematic glyph and re-export.
For details on manual hinting, see Manual hinting.

#### Flex Hints

Flex hints: Nodes 1 and 3 are on the same level and inside the alignment zone, node 2 should be exactly on the flat edge of the zone.
The handles must stay inside the space defined by nodes 1 through 3.

If the font has cupped serifs or slightly tapered stems, the autohinter can automatically apply so-called flex hints.
Flex hints suppress the display of such shallow curves at low resolutions.
They cannot be set manually but are automatically applied when the font is exported.
For flex hinting to kick in, a few conditions must be met.

First, the blueShift value must at least be set to the depth of the cups plus one.
For example, if the serifs are cupped 5 units deep, blueShift should be set to 6 or more.
Set blueShift as a custom parameter in “File” → “Font Info…” → “Font” (Cmd-I).

Secondly, there are a few outline requirements.
The cup or tapering must be built from exactly two consecutive outline segments between three nodes.
The segments do not need to be symmetrical.
The first and third nodes must share the same _{X} coordinate (for tapered stems) or the same _{Y} coordinate (for cupped serifs).
The four handles need not be entirely horizontal (serifs) or vertical (stems), but the three nodes must be placed on the extremes of the two segments.
The overall depth must not exceed 20 units.

Thirdly, in the case of cupped serifs, it is recommended that the three points are completely submerged in the respective alignment zone.
For best results, the second node (in the middle) should be precisely on the flat edge of the zone.
And the other two nodes must reach into the zone.
This means that cupped bottom serifs reach a little bit below the baseline and into its bottom zone, which may seem counter-intuitive at first.