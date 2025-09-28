### Other Settings

#### Grid Spacing & Subdivision

The points defining the outlines are placed on a grid, and the “Grid Spacing” defines how the coordinates of the points are rounded.
The default value of a grid spacing of 1 rounds points to font units.
For example, (3.142, 7.816) is rounded to (3, 7).
A value of 5 rounds points to the nearest factor of 5; consequently (3.142, 7.816) is now rounded to (5, 10).
Finally, a value of 0 does not round points and maintains (3.142, 7.816) as it is.

Contrary to popular belief, decimal coordinates can be exported into CFF-flavor (PostScript) fonts.

Disabling rounding can be helpful for highly detailed designs such as ornaments or when glyphs are scaled to a new size.
Higher values are useful in coarse designs such as pixel fonts.

All tools and modifications snap to the grid.
Choose “Path” → “Round Coordinates” to round all selected points to the grid.

Use a “Subdivision” value above 1 to offer finer control while keeping a large grid spacing for the design coordinates.
For example, a “Grid Spacing” of 100 and a “Subdivision” of 5 places points on a 20 unit subgrid.
A default “Grid Spacing” of 1 with a “Subdivision” of 10 gives point coordinates one decimal point, such as (3.1, 7.8).

#### Keyboard Increments

Many places in Glyphs allow modifying values with the arrow keys.
For example, points can be moved in Edit View, or numeric values in text fields can be incremented and decremented using the Up and Down arrow keys.
Values are modified by 10 units when holding down the Shift key and by 100 units when holding down the Command key.
Adjust the Shift and Command values as desired.

#### Use Custom Naming

Select the “Use Custom Naming” option to use custom glyph names that do not conform to the names from the built-in glyph database.
Enable this option for workflows using custom glyph names, thus preventing the automatic replacement of names.

Deactivating the “Use Custom Naming” option will not immediately rename the glyphs of the font.
Instead, choose “Glyph” → “Update Glyph Info” to update the properties, including the glyph name, of all selected glyphs.
Note that it may invalidate imported or manually written feature code, which will require manual code adjustments.

When importing OpenType fonts or UFO sources, glyph names are either kept or modified to conform with the built-in glyph database.
Go to “Settings” → “User Settings” to change the setting of the option “Keep Glyph Names from Imported Files” (see User Settings).

#### Disable Automatic Alignment

This option disables the automatic alignment of components and the automatic synchronization of metrics for composite glyphs such as diacritics.
Lock the position of individual components by choosing “Lock Component” from the context menu in Edit View.
Go to “Glyphs” → “Settings…” → “User Settings” → “Disable Automatic Alignment for Imported Files” for the setting of imported files (see User Settings).
See also Automatic Alignment.

#### Keep Alternates Next to Base Glyph

Select “Keep Alternates Next to Base Glyphs” to sort glyph variants with a dot suffix name directly after the base glyph without the dot suffix.
For example, a.ss15, a.alt, and a.loclDEU will follow the a glyph instead of being placed after all base lowercase letters.

#### File Format Version

The format of a Glyphs file changed slightly from Glyphs 2 to Glyphs 3.
For compatibility, Glyphs 3 can read and write the old Glyphs 2 file format.

When working on a Glyphs file created in Glyphs 2, Glyphs 3 will import it as a version 2 file.
Some of the features new in Glyphs 3 cannot be stored in version 2 format files.
Use all Glyphs features by changing this setting to “Version 3”.
New Glyphs files are always created in version 3 format.

#### Font Type

The font type controls the type of interpolation used for static instances.
“Default” interpolation is based on Adobe’s Multiple Master model.
This is the interpolation that Glyphs exclusively used before variable fonts, and it continues to be the default for all new documents.
“Variable” interpolation mimics the interpolation used by variable fonts.
Using this interpolation for static instances might be helpful in cases where both static and variable fonts are exported and the differences between the two should be kept to a minimum.