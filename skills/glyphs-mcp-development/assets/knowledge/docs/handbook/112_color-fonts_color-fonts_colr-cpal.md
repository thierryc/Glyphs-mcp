### COLR/CPAL Fonts

Microsoft-style color fonts are fonts that contain two additional tables: `CPAL` (Color Palette) and `COLR` (Color).
These color fonts work like layered color fonts, but they export all color layers to a single font file instead of exporting one font file per layer.

#### Defining the Color Palette

In “File” → “Font Info…” → “Font”, add the Color Palettes custom parameter.
Click its value to edit the color palette.

Click the plus  button to add additional colors to the palette.
Each color is identified by a color index counting up from 0.
Change colors by clicking a color  swatch and choosing a different value with the color picker.
Select a row and click the minus  button to delete a color.

Multiple color palettes can be defined.
Add additional color palettes by choosing “Add Palette” from the gear  menu.
Click the column heading of a palette to remove it with “Remove Palette”.
See COLR/CPAL Fonts: Exporting for details on choosing a palette for each instance.

Confirm the edits to the color palettes with “OK”, or click “Cancel” to discard all edits and keep the palettes as they were.

#### Master Layer as Fallback

`CPAL`/`COLR` color fonts are not supported by all applications.
In case an app cannot handle the color information, it displays the master layer.
The master is not displayed in apps that support `CPAL`/`COLR` color fonts.

#### Color Palette Layers

Add color layers by clicking the plus  button in the “Layers” palette (“Window” → “Palette”, Cmd-Opt-P) and choose “Color Palette” from the context menu on the layer.
Pick a color from the color palette by clicking the color swatch to the right of the layer name.
Choose either a predefined color or the asterisk (*) option.
The asterisk option uses the color that the font user defines.
Glyphs previews this color in black (or in white, for the dark system appearance).

Color Palette layers are named “Color” and the color index from the Color Palettes custom parameter.
Multiple layers of a glyph can have the same color, and some colors of the palette might not be used at all in a glyph.
Not all glyphs need to have the same number of color layers: some might only have a single color layer, while others have multiple layers for each color.

#### Exporting

Exported instances of `CPAL`/`COLR` fonts use the first color palette by default.
Add the Color Palette for CPAL custom parameter to an instance in “File” → “Font Info…” → “Exports” to choose a different color palette for that instance.
Note that the color palette IDs start at 0 for the first palette.
Add additional palettes as described in Defining the Color Palette.

Remove all colors from an instance by adding an Export COLR Table custom parameter and unchecking it.
This will use just the fallback layer and discard the `CPAL` and `COLR` tables.

Glyphs can also convert a `CPAL`/`COLR` font to an SVG color font by adding the following custom parameters in “File” → “Font Info…” → “Exports”:

- Check the Color Layers to SVG custom parameter.

- Set Color Palette for SVG to the number of the palette that should be used for the conversion. Palettes are numbered starting at “0”. The palette number is written in the column header in the Color Palettes custom parameter.

- Check the Export SVG Table custom parameter for the SVG data to be included in the export.