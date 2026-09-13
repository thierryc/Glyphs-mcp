### Autohinting

The technical details of TT hinting are too complex to mix manual and automatic hints.
Therefore, checking the “Autohint” option when exporting a TrueType flavor font will ignore any manual TT hints in the Glyphs file:

Glyphs uses TTF Autohint for autohinting TrueType fonts.

For information on TTF Autohint, refer to the official website.

TTF Autohint can be configured in “File” → “Font Info…” → “Export” (Cmd-I) with the TTFAutohint options and TTFAutohint control instructions custom parameters.
See Show Point Indexes for details on how to get the point indexes needed for the control instructions.

If the “Autohint” export option is not checked, Glyphs includes the manual TT hinting instructions in the exported font.
Automatic hinting can also be used as a starting point for manual hinting; see Instructions for details.