### Font

The “Font” tab contains information that applies to all exported font files.
Click the plus  button to the right of the “General” heading to add additional fields.

#### Family Name

The fontName is the name given to the exported fonts.
This name will appear in font menus.
Fonts with the same family name will be grouped into the same styles submenu.
A family name should only contain ASCII letters (a–z and A–Z), digits (0–9), and spaces.
Any other characters may prevent the fonts from exporting or installing.

Add the familyNames field to provide a family name containing non-ASCII characters or to localize the family name into multiple languages.
Click the plus  button to the right of the “General” heading, select familyNames, and click “Add”.

Name IDs refer to the entries of the OpenType Naming Table stored in OTF and TTF fonts.
See the OpenType `name` table specification for a list of all possible name table entries.

Glyphs uses the family name to derive the file name and the entries for the Name IDs 1, 3, 4, and 6.
In PostScript/CFF-based OpenType fonts, the family name is also used for the _{FontName} and _{FullName} in the `CFF` table.
Add the postscriptFontName and postscriptFullName fields in “File” → “Font Info…” → “Font” → “General” to control those values independently of the family name.

The font name can be overwritten by instances using the familyNames field.

#### Units per Em

The unitsPerEm (UPM) determines the number of coordinate units in the em square of each glyph.
Increasing the UPM can improve the representation of fine details, as it increases the placement options of the nodes.
1000 UPM is the default for new Glyphs files.
The OpenType specification allows values between 16 (2^{4}) and 16,384 (2^{14}), but values above 5000 can lead to problems in Adobe InDesign and Illustrator.
Some applications have issues with values above 3000 UPM.

Additionally, the coordinates of points (nodes and handles) may not exceed ±32,768, and glyph widths in PostScript/CFF-flavor fonts can be problematic beyond 4096 UPM (2^{12}).
Thus, if the design of the font requires higher precision, it may be better to change the “Grid Spacing” and “Subdivision” values.
See Grid Spacing & Subdivision for more details.

Click the double-arrow  button next to the text field to scale the entire font to a different UPM.
Scaling changes the UPM and glyph outlines together, keeping the apparent size of the glyph outlines the same.
Enlarge all glyph outlines of the font by setting the UPM to a smaller value without scaling (for example, from 1000 to 800) and then scale  the UPM back to its original value (for example, 1000).
Change the UPM to a smaller value and scale back to the original UPM for smaller outlines.

Consider using the Scale to UPM custom parameter on an instance to change the UPM value for exported files, scaling glyph outlines and metrics to fit the new UPM value.
Use the unitsPerEm custom parameter to change the UPM without scaling outlines or metrics.

#### Version

The version field is split into a major and minor version, separated by a period.
The version of a new Glyphs file is “1.000”.
Click the stepper buttons to change the minor version.

See the OpenType `head` specification for more details.

The major and minor versions of the font are written as the “fontRevision” entry in the Header table (`head`) of the font.
Additionally, Glyphs derives the Version String (Name ID 5) from the “Version” entry by appending its own version to the font version before writing the version string.
For example, “Version 1.000;Glyphs 3.2 (3245)”.

Use the versionString parameter to define a custom version string.
Note that some applications require this version string to begin with “Version” followed by the major version, a period, and the minor version.
Consult the OpenType specification for details.

#### Creation Date

The date field is used for the “created” and “modified” dates in the `head` table.
Update its value to the current date and time by clicking the update  button.

#### Axes

The “Axes” define design axes for interpolation and variable fonts.
Click the plus  button to the right of the “Axes” heading to add a new axis.
An axis has a name, a four-character tag, and can be hidden or not.

Glyphs offers a range of predefined axis names.
Selecting one of the predefined names will change the tag.
Select the “Hidden” checkbox to hide the axis from font users.

See Interpolation for details on working with axes across multiple masters, and specifically Setting up Axes for details on the usage of axes in variable fonts.

#### Custom Parameters

Additional font configurations can be specified using custom parameters.
Click the plus  button to the right of the “Custom Parameters” heading to add a new parameter.
A list of custom parameters is shown.
Use the search or scroll the list to find the desired parameter.
Click a parameter name in the list to get a description, and click “Add” to add the selected parameters to the font.