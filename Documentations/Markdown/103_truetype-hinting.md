## TrueType Hinting

TrueType (TT) hinting optimizes the display of TrueType fonts at low screen resolutions.
PostScript/CFF flavor OpenType fonts use a different hinting method; see PostScript Hinting for details.

TrueType fonts employ quadratic splines.
These are different from the PostScript-style cubic splines that Glyphs uses.
When exporting to TrueType, all paths are converted to TrueType-style outlines on the fly, including all manually set hinting instructions.

Glyph-level TT hints, like PostScript hints, need to be defined for only the main master.
By default, that is the first master in the masters list.
Set the Get Hints From Master custom parameter in “File” → “Font Info…” → “Font” (Cmd-I) to mark a different master as the main master.