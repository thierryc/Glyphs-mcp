### Layered Color Fonts

The four fonts which result in the stacked text.

Layered color fonts are separate fonts that are stacked on top of each other.
For such a font to work properly, the software environment in which it is used must support the stacking of text layers.

#### Initial Setup

Layered color fonts have a color axis.
Add it in “File” → “Font Info…” → “Font” by clicking the plus  button next to the “Axes” heading.
Name the axis “Color” and use a four-letter tag such as “COLR”.

Each color gets its own master.
Contrary to most other fonts, the masters of a layered color font are not interpolated.
This means that the masters of a layered color font are not required to be compatible for interpolation.
Signal this to Glyphs by adding the Enforce Compatibility Check custom parameter in the “Font” tab and unchecking it:

With this parameter disabled, add masters for each color layer.
Give each master a descriptive name like “Front”, “Inside Light”, “Inside Shadow”, or “Outer Shadow”.
In the “Axes Coordinates” section, set a different numeric “Color” value for each master; for example, 1 for the first master and 2 for the second.

Pro Tip:

Additionally, add a Master Color Dark custom parameter to use a different color for the dark system appearance.

Add a Master Color custom parameter to each master to define its preview color.
Note that custom parameters can also be added when multiple masters are selected.
This color is only used inside Glyphs; the font user can set the exported font files in any color.
Drag the “Opacity” slider in the color picker to use a semitransparent color for the preview.

Switch to the “Exports” tab, click the plus  button located in the bottom-left and choose “Add Instance for each Master”.
This will add an exporting instance for each axis coordinate of the “Color” axis.

#### Editing Color Layers

Edit color layers like normal master layers in Edit View.
By default, the currently selected master is shown.
Click the eye / buttons in the “Layers” palette to view multiple layers at the same time.
When working with layered color fonts, it is common to show  all master layers.

The order of the masters in “File” → “Font Info…” → “Masters” is reflected in Edit View: the first master is shown on top, the second master one layer below, and so on.

#### Exporting

Layered color fonts are exported as separate font files, one for each color layer.
These color layers use the instances as described in Initial Setup.

Glyphs can also convert a layered color font to an SVG color font that includes all color layers in a single font file.
For that, add a new instance in “File” → “Font Info…” → “Exports” and add the Color Layers to SVG custom parameter.
Then, add the Export SVG Table custom parameter to the same instance for the SVG data to be included in the export.
Ensure that the checkboxes of both custom parameters are checked.